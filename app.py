import os
from datetime import date, datetime

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///finance.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to view your financial workspace."


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    incomes = db.relationship("Income", backref="user", lazy=True, cascade="all, delete-orphan")
    expenses = db.relationship("Expense", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    received_on = db.Column(db.Date, nullable=False, default=date.today)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    @property
    def activity_date(self):
        return self.received_on


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    spent_on = db.Column(db.Date, nullable=False, default=date.today)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    @property
    def activity_date(self):
        return self.spent_on


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def money(value):
    return f"${value:,.2f}"


def build_advice(income_total, expense_total, category_totals):
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            prompt = f"Give one concise, practical personal finance recommendation. Income: {income_total:.2f}. Expenses: {expense_total:.2f}. Categories: {category_totals}. Avoid investment advice and do not mention being an AI."
            response = genai.GenerativeModel("gemini-1.5-flash").generate_content(prompt)
            if response.text:
                return response.text.strip()
        except Exception:
            pass
    if income_total <= 0:
        return "Add your first income entry to unlock a more personal monthly plan."
    savings = income_total - expense_total
    ratio = expense_total / income_total
    if ratio > 0.9:
        return "Your spending is using most of your income. Pause non-essential purchases and set a weekly limit until your buffer grows."
    if category_totals:
        category, amount = max(category_totals.items(), key=lambda item: item[1])
        return f"You are currently spending the most on {category.lower()} ({money(amount)}). Review that category for one small reduction this month."
    if savings > 0:
        return f"You have {money(savings)} left after tracked spending. Move part of it to an emergency fund before it gets absorbed by incidental costs."
    return "Track a few more expenses and your advisor will surface a clear saving opportunity."


@app.template_filter("money")
def money_filter(value):
    return money(value or 0)


@app.context_processor
def inject_now():
    return {"today": date.today()}


@app.route("/")
def index():
    return redirect(url_for("dashboard")) if current_user.is_authenticated else redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 8:
            flash("Use your name, a valid email, and a password of at least 8 characters.", "error")
        elif User.query.filter_by(email=email).first():
            flash("That email is already registered.", "error")
        else:
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
        if user and user.check_password(request.form.get("password", "")):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Email or password is incorrect.", "error")
    return render_template("login.html")


@app.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    if request.method == "POST":
        entry_type = request.form.get("entry_type")
        try:
            amount = float(request.form.get("amount", 0))
            entry_date = datetime.strptime(request.form.get("entry_date"), "%Y-%m-%d").date()
            if amount <= 0:
                raise ValueError
            if entry_type == "income":
                db.session.add(Income(source=request.form.get("description", "Income").strip() or "Income", amount=amount, received_on=entry_date, user_id=current_user.id))
            else:
                db.session.add(Expense(description=request.form.get("description", "Expense").strip(), category=request.form.get("category", "Other"), amount=amount, spent_on=entry_date, user_id=current_user.id))
            db.session.commit()
            flash("Entry added to your plan.", "success")
        except (ValueError, TypeError):
            flash("Enter a valid positive amount and date.", "error")
        return redirect(url_for("dashboard"))

    incomes = Income.query.filter_by(user_id=current_user.id).order_by(Income.received_on.desc()).all()
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.spent_on.desc()).all()
    income_total = sum(item.amount for item in incomes)
    expense_total = sum(item.amount for item in expenses)
    category_totals = {}
    for expense in expenses:
        category_totals[expense.category] = category_totals.get(expense.category, 0) + expense.amount
    return render_template("dashboard.html", incomes=incomes, expenses=expenses, income_total=income_total, expense_total=expense_total, savings=income_total - expense_total, category_totals=category_totals, advice=build_advice(income_total, expense_total, category_totals))


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "1") == "1")