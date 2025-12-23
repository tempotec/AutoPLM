from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Length


class CreateUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    role = SelectField('Perfil',
                       choices=[('stylist', 'Estilista'), ('admin', 'Administrador')],
                       default='stylist')
    submit = SubmitField('Create User')


class SettingsForm(FlaskForm):
    username = StringField('Nome Completo', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    submit = SubmitField('Salvar Alterações')
