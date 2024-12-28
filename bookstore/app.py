from flask import Flask, flash, render_template, request, redirect, url_for, jsonify
import mysql.connector
from config import DB_CONFIG

app = Flask(__name__) #调用Flask
app.secret_key = '11111111'  # 设置SECRET_KEY
# 数据库连接函数
def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

# 获取所有书籍
@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM Books") #查询所有书籍信息
    books = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('index.html', books=books) #在index.html中将数据输出，放在首页中




# 进货页面
@app.route('/suppliers', methods=['GET', 'POST'])
def suppliers():
    if request.method == 'POST':
        data = request.form
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute( #插入语句，通过MYSQL中触发器对books进行更新
                "INSERT INTO Suppliers (book_id, price, number, name, contact_info, supply_date) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (data['book_id'], data['price'], data['number'], data['name'], data.get('contact_info', ''), data['supply_date'])
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('index'))  # 重定向到主页，刷新书籍信息
    return render_template('suppliers.html')

# 购买页面
# 获取书籍价格（AJAX请求）
@app.route('/get_book_price/<int:book_id>', methods=['GET'])
def get_book_price(book_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT price FROM Books WHERE book_id = %s", (book_id,)) #查询书籍价格并打印
    book = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if book:
        return jsonify({'price': book['price']})
    else:
        return jsonify({'price': None})

# 购买页面
@app.route('/sales', methods=['GET', 'POST'])
def sales():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM Books")
    books = cursor.fetchall()
    cursor.close()
    conn.close()

    if request.method == 'POST':
        data = request.form
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute( #插入购买信息
                "INSERT INTO Sales (book_id, quantity, sale_price, sale_date, customer_id) "
                "VALUES (%s, %s, %s, %s, %s)",
                (data['book_id'], data['quantity'], data['sale_price'], data['sale_date'], data['customer_id'])
            )
            conn.commit()
        except mysql.connector.Error as e:
            conn.rollback()
            print(f"Error: {e}")
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('index'))  # 重定向到主页，刷新书籍信息
    
    return render_template('sales.html', books=books)


#退货
@app.route('/returns', methods=['GET', 'POST'])
def returns():
    if request.method == 'POST':
        data = request.form
        book_id = data['book_id']
        quantity = int(data['quantity'])
        customer_id = data['customer_id']
        return_date = data['return_date']

        # 连接数据库
        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查该书籍在退货前是否有足够的购买记录
        cursor.execute("""
            SELECT SUM(quantity) 
            FROM Sales 
            WHERE book_id = %s AND sale_date <= %s AND customer_id = %s
        """, (book_id, return_date, customer_id))
        
        total_purchased = cursor.fetchone()[0] or 0

        if total_purchased >= quantity:
            try:
                # 执行退货操作
                cursor.execute("""
                    INSERT INTO Returns (book_id, quantity, return_date, customer_id) 
                    VALUES (%s, %s, %s, %s)
                """, (book_id, quantity, return_date, customer_id))
                conn.commit()
                flash("退货成功！")
            except Exception as e:
                conn.rollback()
                flash(f"退货失败: {e}")
        else:
            flash("退货信息错误，无法退货！")

        cursor.close()
        conn.close()
        return redirect(url_for('returns'))

    return render_template('returns.html')





@app.route('/statistics', methods=['GET'])
def statistics():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取月份参数
    month = request.args.get('month', None)
    stats = None

    if month:
        # 查询销售总额
        query_sales_total = """
            SELECT SUM(sale_price * quantity) 
            FROM Sales 
            WHERE DATE_FORMAT(sale_date, '%Y-%m') = %s
        """
        cursor.execute(query_sales_total, (month,))
        total_sales = cursor.fetchone()[0] or 0

        # 查询退货总额，连接 Sales 表获取 sale_price
        query_returns_total = """
            SELECT SUM(s.sale_price * r.quantity)
            FROM Returns r
            JOIN Sales s ON r.book_id = s.book_id
            WHERE DATE_FORMAT(r.return_date, '%Y-%m') = %s
        """
        cursor.execute(query_returns_total, (month,))
        returns_total = cursor.fetchone()[0] or 0

        # 计算最终的销售总额（销售 - 退货）
        total_sales -= returns_total

        # 查询销售总量（销售总量 - 退货总量）
        query_sales_quantity = """
            SELECT SUM(quantity) 
            FROM Sales 
            WHERE DATE_FORMAT(sale_date, '%Y-%m') = %s
        """
        cursor.execute(query_sales_quantity, (month,))
        total_quantity = cursor.fetchone()[0] or 0

        # 查询退货总量
        query_returns_quantity = """
            SELECT SUM(quantity) 
            FROM Returns 
            WHERE DATE_FORMAT(return_date, '%Y-%m') = %s
        """
        cursor.execute(query_returns_quantity, (month,))
        returns_quantity = cursor.fetchone()[0] or 0

        # 计算最终的销售总量（销售 - 退货）
        total_quantity -= returns_quantity

        # 查询畅销书排行（按销售数量排序，扣除退货数量）
        query_top_selling_books = """
            SELECT s.book_id, 
                   SUM(s.quantity) - IFNULL(SUM(r.quantity), 0) AS total_quantity
            FROM Sales s
            LEFT JOIN Returns r ON s.book_id = r.book_id AND DATE_FORMAT(r.return_date, '%Y-%m') = %s
            WHERE DATE_FORMAT(s.sale_date, '%Y-%m') = %s
            GROUP BY s.book_id
            ORDER BY total_quantity DESC
            LIMIT 10
        """
        cursor.execute(query_top_selling_books, (month, month))
        top_selling_books = cursor.fetchall()

        # 如果查询结果为空，给 top_books_info 赋一个默认值
        if not top_selling_books:
            top_books_info = "无畅销书"
        else:
            # 格式化畅销书信息
            top_books_info = ", ".join([f"书籍ID: {book[0]} - 销售量: {book[1]}本"
                                        for book in top_selling_books])

        stats = (total_sales, total_quantity, top_books_info)

    conn.close()

    # 如果没有统计结果，给 stats 一个默认值
    if stats is None:
        stats = (0, 0, "无畅销书")

    # 渲染统计结果页面
    return render_template('statistics.html', statistics=stats)





if __name__ == '__main__':
    app.run(debug=True)
