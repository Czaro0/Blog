import os
from flask import Flask, request, render_template, redirect, url_for
from flask_security import Security, UserMixin, RoleMixin, SQLAlchemyUserDatastore, current_user, login_required
from flask_security.forms import RegisterForm, LoginForm
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from wtforms import StringField, PasswordField
from wtforms.validators import InputRequired, DataRequired, Length, EqualTo, ValidationError
from datetime import datetime

class CustomLoginForm(LoginForm):
    email = StringField('Email', validators=[InputRequired(message="Pole email jest wymagane.")])
    password = PasswordField('Hasło', validators=[InputRequired(message="Pole hasło jest wymagane.")])

class ExtendedRegisterForm(RegisterForm):
    email = StringField('Email', validators=[DataRequired()])
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Ten email jest już przypisany do konta.')
        
    nickname = StringField('Nickname', validators=[DataRequired(), Length(min=3, max=20)])
    def validate_nickname(self, nickname):
        user = User.query.filter_by(nickname=nickname.data).first()
        if user:
            raise ValidationError('Ten nickname jest już zajęty. Wybierz inny.')
        
    password_confirm = PasswordField(
        'Potwierdź hasło',
        validators=[DataRequired(), EqualTo('password', message='Hasła muszą być identyczne')])
 
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
 
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'Spadajaca_gwiazda_spelnia_sny')
app.config['SECURITY_PASSWORD_SALT'] = os.environ.get('SECURITY_PASSWORD_SALT', 'Najasniejsza_Gwiazda')
app.config['SECURITY_REGISTERABLE'] = True
app.config['SECURITY_SEND_REGISTER_EMAIL'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
 
db = SQLAlchemy(app)
 
roles_user = db.Table(
    'roles_users',
    db.Column('user_id', db.ForeignKey('user.id')),
    db.Column('role_id', db.ForeignKey('role.id')),
)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user_nickname = db.Column(db.String(20), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'))
 
    user = db.relationship('User', backref='comments')
    post = db.relationship('Post', backref=db.backref('comments', lazy='dynamic'))

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(255))  # Ścieżka do obrazu
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user_nickname = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime)

    user = db.relationship('User',backref='posts')
 
class Role(db.Model, RoleMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True)
    description = db.Column(db.String(128))
 
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    nickname = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, default=True)
    confirmed_at = db.Column(db.DateTime)
    fs_uniquifier = db.Column(db.String(255), unique=True, nullable=False) 
    roles = db.relationship('Role', secondary=roles_user, backref=db.backref('users'))
 
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        if not self.fs_uniquifier:
            import uuid
            self.fs_uniquifier = str(uuid.uuid4())
 
user_datastore = SQLAlchemyUserDatastore(db, User, Role)

app.config['SECURITY_REGISTERABLE'] = True
app.config['SECURITY_SEND_REGISTER_EMAIL'] = False

security = Security(app, user_datastore, register_form=ExtendedRegisterForm)
 
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
 
@app.route('/')
def index():
    if current_user.is_authenticated:
        posts = Post.query.order_by(Post.timestamp.desc()).all()
        return render_template('index.html', posts=posts)
    else:
        return redirect(url_for('security.login'))
 
@app.route('/create-post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        file = request.files['image']
        image_filename = None
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_filename = filename
 
        new_post = Post(
            title=title,
            content=content,
            image=image_filename,
            user_id=current_user.get_id(),
            user_nickname=current_user.nickname,
            timestamp = datetime.now()
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for('index'))
 
    return render_template('create_post.html')

@app.route('/add-comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    content = request.form['content']
    new_comment = Comment(
        content=content,
        user_id=current_user.get_id(),
        user_nickname=current_user.nickname,
        post_id=post_id,
        timestamp=datetime.now())
    db.session.add(new_comment)
    db.session.commit()
    return redirect(url_for('post_detail', post_id=post_id))

@app.route('/post/<int:post_id>')
@login_required
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post_detail.html', post=post)

@app.route("/delete-post/<int:post_id>", methods=["POST"])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.get_id():
        return "Nie masz uprawnień do usunięcia tego wpisu.", 403
    if post.image:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], post.image)
        if os.path.exists(image_path):
            os.remove(image_path)
 
    db.session.delete(post)
    db.session.commit()
    return redirect(url_for('index'))
 
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
 
    app.run(host='0.0.0.0', port=5001, debug=True)