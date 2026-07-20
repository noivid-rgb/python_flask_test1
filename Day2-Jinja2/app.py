from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# 使用記憶體（List）模擬臨時資料庫
messages_db = [
    {"name": "Admin", "content": "歡迎來到 Day 2 留言板！"},
    {"name": "Peter", "content": "Flask 真係好方便！"}
]


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # 1. 獲取表單提交的內容
        sender_name = request.form.get('username')
        sender_msg = request.form.get('message')

        # 2. 簡易驗證
        if sender_name and sender_msg:
            # 3. 儲存至臨時資料庫
            messages_db.append({"name": sender_name, "content": sender_msg})

        # 4. 提交完畢後，重導向回首頁（防止重新整理網頁時重複提交表單）
        return redirect(url_for('index'))

    # GET 請求：渲染頁面並將留言清單傳入 HTML
    return render_template('guestbook.html', messages=messages_db)


if __name__ == '__main__':
    app.run(debug=True)
