from flask import Flask

app = Flask(__name__)

#http://address/
@app.route("/")

@app.route("/index")
def index():
    return "Index page"

@app.route("/hello")
@app.route("/hello/<name>")
#def hello (name):
def hello (name='Nobody'):
 return f'hello: {name}'
