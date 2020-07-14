import os
import datetime

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Find current user
    user_id = int(session['user_id'])

    # cashLeft represents how much cash the user has left
    cashRow = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=user_id)
    cashLeft = round(cashRow[0]['cash'], 2)

    # Get lists of stocks with symbols, names, shares, current price, and total
    stockList = db.execute("""SELECT symbol, stock, shares, price, total
    FROM portfolio WHERE user_id=:user_id""", user_id=user_id)

    # totalVal represents the total value of all stocks purchased
    totalVal = 0
    for row in stockList:
        totalVal += row["total"]
    totalVal = round(totalVal + cashLeft, 2)

    return render_template("index.html", cashLeft = cashLeft, stockList=stockList, totalVal=totalVal)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")

    if request.method == "POST":
        # If the user didn't enter a symbol or a number of shares
        if not request.form.get("symbol") or not request.form.get("shares"):
            return apology("You must enter a stock symbol and number of shares!")

        symbol = request.form.get("symbol").upper()
        shares = int(request.form.get("shares"))
        info = lookup(symbol)
        user_id = int(session['user_id'])

        # If the user entered a symbol not relating to a stock
        if not info:
            return apology("The symbol you entered doesn't correspond to a stock", 403)

        # If the user entered a negative number of shares
        if shares <= 0:
            return apology("You must enter a positive number of shares", 403)

        companyName = info["name"]
        price = round(info["price"], 2)

        # Find out how much cash the user has
        cashResult = db.execute("SELECT cash FROM users WHERE id = :userid", userid = user_id)
        cash = float(cashResult[0]['cash'])

        # Find total price of purchase
        totalPrice = price * int(shares)
        cashLeft = round(cash - totalPrice, 2)

        # See if user can afford purchase
        if cashLeft < 0:
            return apology("You cannot afford this many shares")

        # See if user has stock already
        stockExist = db.execute("""SELECT * FROM portfolio WHERE user_id=:user_id AND symbol=:symbol""",
        user_id=user_id, symbol=symbol)

        if len(stockExist) == 1:
            newShares = shares + int(stockExist[0]["shares"])
            # newTotal is the total value of all shares at current price, to be put into index table, not history
            newTotal = newShares*price

            # Update portfolio to show current number of shares and value of stock
            db.execute("""UPDATE portfolio SET shares=:shares, price=:price, total=:total
            WHERE user_id=:user_id AND symbol=:symbol""",
            shares=newShares, price=price, total=newTotal, user_id=user_id, symbol=symbol)

        # Else if first time user is buying this stock
        else:
            # Insert new row into portfolio
            db.execute("""INSERT INTO portfolio (user_id, symbol, stock, shares, price, total)
            VALUES (:user_id, :symbol, :stock, :shares, :price, :total)""",
            user_id=user_id, symbol=symbol, stock=companyName, shares=shares, price=price, total=totalPrice)


        # Update history table to reflect new transaction, total is the total of that transaction
        db.execute("""INSERT INTO history (user_id, stock, shares, time, price, total)
        VALUES (:user_id, :symbol, :shares, :datetime, :price, :total)""",
        user_id=user_id, symbol=symbol, shares=shares, datetime=datetime.datetime.now(), price=price, total=totalPrice)

        # Update user's cash
        db.execute("UPDATE users SET cash = :cashLeft WHERE id=:user_id", cashLeft=cashLeft, user_id=user_id)

        return redirect("/bought")


@app.route("/bought")
@login_required
def bought():
    # Get variables to display portfolio table on bought.html
    user_id = int(session['user_id'])
    cashRow = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=user_id)
    cashLeft = round(cashRow[0]['cash'], 2)
    stockList = db.execute("""SELECT symbol, stock, shares, price, total
    FROM portfolio WHERE user_id=:user_id""", user_id=user_id)
    totalVal = 0
    for row in stockList:
        totalVal += row["total"]
    totalVal = round(totalVal + cashLeft,2)

    return render_template("bought.html", cashLeft=cashLeft, stockList=stockList, totalVal=totalVal)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = int(session["user_id"])

    # Query database for every transaction this user has made
    historyList = db.execute("SELECT * FROM history WHERE user_id=:user_id", user_id=user_id)

    return render_template("history.html", historyList=historyList)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        # Get symbol from quote and run lookup function in helpers.py to insert info into quoted
        symbol = request.form.get("quote")
        if lookup(symbol) == None:
            return apology("The symbol you entered doesn't correspond to a stock", 403)
        else:
            info = lookup(symbol)
            companyName = info["name"]
            price = round(info["price"], 2)
            return render_template("quoted.html", symbol=symbol, companyName=companyName, price=price)



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # GET Method is default, means form wasn't submitted by user so we should just display it
    if request.method == "GET":
        return render_template("register.html")
    else:
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        # Checks if username slot was empty or it exists already
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=username)
        if not username:
            return apology("you must enter a username", 403)
        if len(rows) == 1:
            return apology("username is taken", 403)
        # Check if password is same as confirmation and not empty
        if password != confirmation or not password:
            return apology("the two passwords you entered are not the same", 403)
        elif not password:
            return apology("you must enter a password", 403)
    # Submit user's input via POST to register

    # INSERT new user into users
    db.execute("""INSERT INTO users (username, hash)
    VALUES (:username, :password)""",
    username=username, password=generate_password_hash(password))

    return redirect("/")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # Get a list of stocks the user has to show on the page
    user_id = int(session["user_id"])
    symbolList = db.execute("SELECT symbol FROM portfolio WHERE user_id=:user_id", user_id=user_id)

    if request.method == "GET":
        return render_template("sell.html", symbolList=symbolList)
    if request.method == "POST":
        # Find how much the user wants to sell and of what stock
        shares = request.form.get("shares")
        symbol = request.form.get("symbol")

        # If user doesn't enter a symbol, render apology
        if not symbol:
            return apology("You must enter a symbol")

        # IF user doesn't enter shares, render apology
        if not shares:
            return apology("You must enter a number of shares")

        # Get info on current price of stock and number of shares user has, assign variables
        shares = int(shares)
        info = lookup(symbol)
        stockList = db.execute("SELECT * FROM portfolio WHERE user_id=:user_id AND symbol=:symbol",
        user_id=user_id, symbol=symbol)
        price = round(info["price"], 2)
        userShares = int(stockList[0]["shares"])
        totalSale = round((shares * price), 2)
        stockVal = round((userShares * price), 2)
        newTotal = stockVal - totalSale

        # Find out how much cash the user has after sale
        cashList = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=user_id)
        cash = round(cashList[0]["cash"], 2)
        cashLeft = totalSale + cash

        # Render apology if user doesn't have enough shares to sell or doesn't own stock
        if userShares < shares:
            return apology("You don't own enough shares of this stock")

        # If all else is well, update portfolio and history to reflect the sale

        # If user is selling all their shares, delete row from portfolio
        elif userShares == shares:
            db.execute("DELETE FROM portfolio WHERE user_id=:user_id AND symbol=:symbol",
            user_id=user_id, symbol=symbol)
        # Else, update portfolio
        else:
            newShares = userShares - shares
            db.execute("""UPDATE portfolio SET shares=:shares, price=:price, total=:total
            WHERE user_id=:user_id AND symbol=:symbol""", shares=newShares, price=price,
            total=newTotal, user_id=user_id, symbol=symbol)

        # Add transaction to history table, total is the total of that transaction
        db.execute("""INSERT INTO history (user_id, stock, shares, time, price, total)
        VALUES (:user_id, :symbol, :shares, :datetime, :price, :total)""",
        user_id=user_id, symbol=symbol, shares=shares, datetime=datetime.datetime.now(),
        price=(-1)*price, total=(-1)*totalSale)

        # Update user's cash
        db.execute("UPDATE users SET cash = :cashLeft WHERE id=:user_id", cashLeft=cashLeft, user_id=user_id)

        return redirect("/sold")


@app.route("/sold")
@login_required
def sold():
    # Get variables to display portfolio table on sold.html
    user_id = int(session['user_id'])
    cashRow = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=user_id)
    cashLeft = round(cashRow[0]['cash'], 2)
    stockList = db.execute("""SELECT symbol, stock, shares, price, total
    FROM portfolio WHERE user_id=:user_id""", user_id=user_id)
    totalVal = 0
    for row in stockList:
        totalVal += row["total"]
    totalVal = round(totalVal + cashLeft,2)

    return render_template("sold.html", cashLeft=cashLeft, stockList=stockList, totalVal=totalVal)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

# Give user the option to add cash
@app.route("/addcash", methods=["GET", "POST"])
@login_required
def addcash():
    user_id = int(session["user_id"])
    if request.method == "POST":
        # Make sure user enters a valid dollar amount
        if not request.form.get("cash"):
            return apology("You must enter a valid dollar amount")

        # Get how much cash the user added and how much they had before
        cashAdd = round(float(request.form.get("cash")), 2)
        cashRow = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=user_id)
        cashLeft = round(cashRow[0]["cash"],2)
        cashAfter = cashLeft + cashAdd

        # Update users to reflect change
        db.execute("UPDATE users SET cash=:cashAfter WHERE id=:user_id", cashAfter=cashAfter, user_id=user_id)

        # Update history to show transaction
        db.execute("""INSERT INTO history (user_id, stock, shares, time, price, total)
        VALUES (:user_id, :stock, :shares, :time, :price, :total)""",
        user_id=user_id, stock="ADD CASH", shares=1, time=datetime.datetime.now(), price=cashAdd, total=cashAdd)

        # Get lists of stocks with symbols, names, shares, current price, and total
        stockList = db.execute("""SELECT symbol, stock, shares, price, total
        FROM portfolio WHERE user_id=:user_id""", user_id=user_id)

        # totalVal represents the total value of all stocks purchased
        totalVal = 0
        for row in stockList:
            totalVal += row["total"]
        totalVal = round(totalVal + cashAfter, 2)

        # Return to homepage
        return render_template("cashadded.html", stockList=stockList, cashLeft=cashAfter, totalVal=totalVal)

