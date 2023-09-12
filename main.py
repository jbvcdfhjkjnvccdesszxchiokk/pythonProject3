import psycopg2
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = '123'
# Функция для подключения к базе данных PostgreSQL
def connect_to_database():
    try:
        connection = psycopg2.connect(
            database='my_store',
            user='postgres',
            password='aleksis2002',
            host='127.0.0.1',
            port='5432'
        )
        return connection
    except psycopg2.Error as e:
        print("Ошибка при подключении к базе данных:", e)
        return None

# Функция для выполнения SQL-запросов
def execute_query(query, params=None, fetch=True):
    conn = connect_to_database()
    if conn is None:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetch:
            result = cursor.fetchall()
        else:
            result = None
        conn.commit()
        return result
    except psycopg2.Error as e:
        print("Ошибка при выполнении SQL-запроса:", e)
    finally:
        conn.close()

def determine_user_role(email):
    # Проверяем email пользователя в соответствующих таблицах
    client = execute_query("SELECT * FROM clients WHERE email = %s", (email,), fetch=True)
    if client:
        return 'client'

    employee = execute_query("SELECT * FROM employees WHERE email = %s", (email,), fetch=True)
    if employee:
        return 'employee'

    general_manager = execute_query("SELECT * FROM general_managers WHERE email = %s", (email,), fetch=True)
    if general_manager:
        return 'general_manager'

    # Если email не найден ни в одной из таблиц, возвращаем None или другое значение по умолчанию
    return None

# Главная страница - форма авторизации
@app.route('/')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Проверка пользователя в базе данных
        role = determine_user_role(email)

        if role == 'client':
            query = "SELECT * FROM clients WHERE email = %s"
        elif role == 'employee':
            query = "SELECT * FROM employees WHERE email = %s"
        elif role == 'general_manager':
            query = "SELECT * FROM general_managers WHERE email = %s"
        else:
            return "Неверный логин или пароль"

        user = execute_query(query, (email,), fetch=True)

        if user and check_password_hash(user[0][3], password):  # Проверка хэша пароля
            session['user_id'] = user[0][0]  # Общий ключ для идентификатора пользователя
            session['role'] = role  # Ключ для роли
            return redirect(url_for('profile'))

    return render_template('login.html')

# Страница регистрации
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        # Проверяем, существует ли уже пользователь с таким email
        existing_user_query = """
            SELECT * FROM clients WHERE email = %s
            UNION ALL
            SELECT * FROM employees WHERE email = %s
            UNION ALL
            SELECT * FROM general_managers WHERE email = %s
        """
        existing_user = execute_query(existing_user_query, (email, email, email), fetch=True)

        if existing_user:
            error = "Пользователь с таким email уже существует."
            return render_template('register.html', error=error)

        # Определяем, в какую таблицу вставлять пользователя в зависимости от его роли
        if role == 'client':
            insert_query = "INSERT INTO clients (name, email, hash_password) VALUES (%s, %s, %s)"
        elif role == 'employee':
            insert_query = "INSERT INTO employees (name, email, hash_password) VALUES (%s, %s, %s)"
        elif role == 'general_manager':
            insert_query = "INSERT INTO general_managers (name, email, hash_password) VALUES (%s, %s, %s)"
        else:
            return "Недопустимая роль"

        # Хэширование пароля
        hashed_password = generate_password_hash(password, method='sha256')

        try:
            # Вставляем нового пользователя в соответствующую таблицу
            execute_query(insert_query, (name, email, hashed_password), fetch=False)

            # Создаем пользователя с помощью CREATE USER
            create_user_query = f"CREATE USER {name} WITH ROLE {role} LOGIN PASSWORD %s"
            execute_query(create_user_query, (hashed_password,), fetch=False)
        except psycopg2.IntegrityError as e:
            error = "Ошибка при регистрации. Пожалуйста, попробуйте ещё раз."
            return render_template('register.html', error=error)

        return redirect(url_for('login'))

    return render_template('register.html')

# Профиль пользователя
@app.route('/profile')
def profile():
    user_id = session.get('user_id')
    role = session.get('role')

    if user_id and role:
        # Используйте user_id и role для извлечения информации о пользователе
        user = None
        template = None

        if role == 'client':
            user = execute_query("SELECT * FROM clients WHERE client_id = %s", (user_id,), fetch=True)
            template = 'client_profile.html'
        elif role == 'employee':
            user = execute_query("SELECT * FROM employees WHERE employee_id = %s", (user_id,), fetch=True)
            template = 'employee_profile.html'
        elif role == 'general_manager':
            user = execute_query("SELECT * FROM general_managers WHERE manager_id = %s", (user_id,), fetch=True)
            template = 'manager_profile.html'

        if user and template:
            return render_template(template, user=user[0])

    return redirect(url_for('login'))

# Выход из учетной записи
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/manager/profile')
def manager_profile():
    user_id = session.get('user_id')
    if user_id:
        user = execute_query("SELECT * FROM general_managers WHERE manager_id = %s", (user_id,), fetch=True)
        if user:
            return render_template('manager_profile.html', user=user[0])
        else:
            return "Менеджер не найден"
    else:
        return redirect(url_for('login'))

# Страница со списком сотрудников менеджера
@app.route('/manager/employee')
def manager_employee():
    user_id = session.get('user_id_manager')  # Получение идентификатора текущего пользователя (менеджера) из сессии

    if user_id:
        # Выполнение SQL-запроса для извлечения списка всех сотрудников
        query = "SELECT * FROM employees"
        employees = execute_query(query, fetch=True)

        # Отобразите список сотрудников в HTML-шаблоне
        return render_template('manager_employee.html', employees=employees)
    else:
        return redirect(url_for('login'))

# Страница со списком заказов менеджера
@app.route('/manager/orders')
def manager_orders():
    user_id = session.get('user_id_manager')  # Получение идентификатора текущего пользователя (менеджера) из сессии

    if user_id:
        # Выполнение SQL-запроса для извлечения списка всех заказов
        query = "SELECT * FROM orders"
        orders = execute_query(query, fetch=True)

        # Отобразите список заказов в HTML-шаблоне
        return render_template('manager_orders.html', orders=orders)
    else:
        return redirect(url_for('login'))

# Страница со списком клиентов менеджера
@app.route('/manager/clients')
def manager_clients():
    user_id = session.get('user_id_manager')  # Получение идентификатора текущего пользователя (менеджера) из сессии

    if user_id:
        # Выполнение SQL-запроса для извлечения списка всех клиентов
        query = "SELECT * FROM clients"
        clients = execute_query(query, fetch=True)

        # Отобразите список клиентов в HTML-шаблоне
        return render_template('manager_clients.html', clients=clients)
    else:
        return redirect(url_for('login'))

# Страница со списком товаров менеджера
@app.route('/manager/goods')
def manager_goods():
    user_id = session.get('user_id_manager')  # Получение идентификатора текущего пользователя (менеджера) из сессии

    if user_id:
        # Выполнение SQL-запроса для извлечения списка всех товаров
        query = "SELECT * FROM goods"
        goods = execute_query(query, fetch=True)

        # Отобразите список товаров в HTML-шаблоне
        return render_template('manager_goods.html', goods=goods)
    else:
        return redirect(url_for('login'))

# Страница для добавления товара менеджером
@app.route('/manager/goods/add_goods', methods=['GET', 'POST'])
def manager_add_goods():
    user_id = session.get('user_id_manager')  # Получение идентификатора текущего пользователя (менеджера) из сессии

    if user_id:
        if request.method == 'POST':
            # Получение данных о товаре из формы
            name = request.form['name']
            category_id = request.form['category_id']
            color_id = request.form['color_id']
            brand_id = request.form['brand_id']
            price = request.form['price']

            # Выполнение SQL-запроса на вставку
            query = "INSERT INTO goods (name, category_id, color_id, brand_id, price) VALUES (%s, %s, %s, %s, %s)"
            params = (name, category_id, color_id, brand_id, price)
            execute_query(query, params, fetch=False)

            return redirect(url_for('manager_goods'))
        else:
            # Если запрос GET, отображаем форму для добавления товара
            return render_template('manager_add_goods.html')
    else:
        return redirect(url_for('login'))

# Страница для удаления товара менеджером
@app.route('/manager/goods/delete_goods', methods=['POST'])
def manager_delete_goods():
    user_id = session.get('user_id_manager')  # Получение идентификатора текущего пользователя (менеджера) из сессии

    if user_id:
        if request.method == 'POST':
            # Получение идентификатора товара, который нужно удалить, из формы
            goods_id = request.form['goods_id']

            # Выполнение SQL-запроса на удаление товара из базы данных
            query = "DELETE FROM goods WHERE goods_id = %s"
            params = (goods_id,)
            execute_query(query, params, fetch=False)

            return redirect(url_for('manager_goods'))
    else:
        return redirect(url_for('login'))

@app.route('/employee/profile')
def employee_profile():
    user_id = session.get('user_id')  # Получение идентификатора текущего пользователя из сессии

    if user_id:
        # Выполнение SQL-запроса для извлечения информации о сотруднике на основе его идентификатора
        query = "SELECT * FROM employees WHERE employee_id = %s"
        params = (user_id,)
        employee = execute_query(query, params, fetch=True)

        if employee:
            # Отобразите информацию о сотруднике в HTML-шаблоне
            return render_template('employee_profile.html', employee=employee[0])
        else:
            return "Сотрудник не найден"
    else:
        return redirect(url_for('login'))

@app.route('/employee/orders')
def employee_orders():
    user_id = session.get('user_id')  # Получение идентификатора текущего пользователя (сотрудника) из сессии

    if user_id:
        # Выполнение SQL-запроса для извлечения списка всех заказов клиентов
        query = "SELECT * FROM orders"
        orders = execute_query(query, fetch=True)

        # Отобразите список заказов в HTML-шаблоне
        return render_template('employee_orders.html', orders=orders)
    else:
        return redirect(url_for('login'))

@app.route('/employee/clients')
def employee_clients():
    user_id = session.get('user_id')  # Получение идентификатора текущего пользователя (сотрудника) из сессии

    if user_id:
        # Выполнение SQL-запроса для извлечения списка всех клиентов
        query = "SELECT * FROM clients"
        clients = execute_query(query, fetch=True)

        # Отобразите список клиентов в HTML-шаблоне
        return render_template('employee_clients.html', clients=clients)
    else:
        return redirect(url_for('login'))

@app.route('/employee/goods')
def employee_goods():
    user_id = session.get('user_id')  # Получение идентификатора текущего пользователя (сотрудника) из сессии

    if user_id:
        # Выполнение SQL-запроса для извлечения списка всех товаров
        query = "SELECT * FROM goods"
        goods = execute_query(query, fetch=True)

        # Отобразите список товаров в HTML-шаблоне
        return render_template('employee_goods.html', goods=goods)
    else:
        return redirect(url_for('login'))

# Страница для добавления товара сотрудником
@app.route('/employee/goods/add_goods', methods=['GET', 'POST'])
def employee_add_goods():
    user_id = session.get('user_id')  # Получение идентификатора текущего пользователя (сотрудника) из сессии

    if user_id:
        if request.method == 'POST':
            # Получение данных о товаре из формы
            name = request.form['name']
            category_id = request.form['category_id']
            color_id = request.form['color_id']
            brand_id = request.form['brand_id']
            price = request.form['price']

            # Выполнение SQL-запроса на вставку
            query = "INSERT INTO goods (name, category_id, color_id, brand_id, price) VALUES (%s, %s, %s, %s, %s)"
            params = (name, category_id, color_id, brand_id, price)
            execute_query(query, params, fetch=False)

            return redirect(url_for('employee_goods'))
        else:
            # Если запрос GET, отображаем форму для добавления товара
            return render_template('employee_add_goods.html')
    else:
        return redirect(url_for('login'))

@app.route('/employee/goods/delete_goods', methods=['POST'])
def employee_delete_goods():
    user_id = session.get('user_id')  # Получение идентификатора текущего пользователя (сотрудника) из сессии

    if user_id:
        if request.method == 'POST':
            # Получение идентификатора товара, который нужно удалить, из формы
            goods_id = request.form['goods_id']

            # Выполнение SQL-запроса на удаление товара из базы данных
            query = "DELETE FROM goods WHERE goods_id = %s"
            params = (goods_id,)
            execute_query(query, params, fetch=False)

            return redirect(url_for('employee_goods'))
    else:
        return redirect(url_for('login'))

@app.route('/client/profile')
def client_profile():
    user_id = session.get('user_id')  # Получение идентификатора текущего пользователя (клиента) из сессии

    if user_id:
        # Здесь вы должны выполнить SQL-запрос для извлечения информации о клиенте из базы данных
        # Пример SQL-запроса, предполагая, что вам нужно извлечь информацию о клиенте по его идентификатору:
        query = "SELECT * FROM clients WHERE client_id = %s"
        params = (user_id,)
        client_info = execute_query(query, params, fetch=True)

        if client_info:
            # Если информация о клиенте найдена, передайте ее в HTML-шаблон и отобразите
            return render_template('client_profile.html', client=client_info[0])
        else:
            return "Информация о клиенте не найдена"
    else:
        return redirect(url_for('login'))

@app.route('/client/orders')
def client_orders():
    user_id = session.get('user_id')  # Получение идентификатора текущего пользователя (клиента) из сессии

    if user_id:
        # Здесь вы должны выполнить SQL-запрос для извлечения списка заказов клиента из базы данных
        # Пример SQL-запроса, предполагая, что вам нужно извлечь заказы клиента по его идентификатору:
        query = "SELECT * FROM orders WHERE client_id = %s"
        params = (user_id,)
        orders = execute_query(query, params, fetch=True)

        # Если заказы найдены, передайте их в HTML-шаблон и отобразите
        return render_template('client_orders.html', orders=orders)
    else:
        return redirect(url_for('login'))


@app.route('/client/goods', methods=['GET', 'POST'])
def client_goods():
    if request.method == 'POST':
        # Получение данных о выбранных товарах из формы
        selected_goods = request.form.getlist('selected_goods')

        # Оформление выбранных товаров и добавление их в таблицу заказов
        if session.get('user_id'):
            user_id = session['user_id']
            for good_id in selected_goods:
                # Здесь вы должны выполнить SQL-запрос для добавления товара в таблицу заказов
                # Пример SQL-запроса для добавления товара в заказ:
                query = "INSERT INTO order_details (order_id, goods_id) VALUES (%s, %s)"
                execute_query(query, (user_id, good_id), fetch=False)
            flash('Товары успешно добавлены в заказ', 'success')
        else:
            flash('Для оформления заказа необходимо войти в систему', 'danger')

    # Здесь вы должны выполнить SQL-запрос для извлечения списка доступных товаров из базы данных
    # Пример SQL-запроса для извлечения всех товаров:
    query = "SELECT * FROM goods"
    goods = execute_query(query, fetch=True)

    # Если товары найдены, передайте их в HTML-шаблон и отобразите
    return render_template('client_goods.html', goods=goods)

if __name__ == '__main__':
    app.run(debug=True)