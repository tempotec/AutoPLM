from app.extensions import db


class FluxogamaSubetapa(db.Model):
    """
    Tabela local de sub-etapas do Fluxogama.
    WSID é o identificador numérico usado na API (sempre string normalizada).
    """
    __tablename__ = 'fluxogama_subetapas'

    id = db.Column(db.Integer, primary_key=True)
    wsid = db.Column(db.String(20), unique=True, nullable=False)  # ex: "14"
    nome = db.Column(db.String(100), nullable=False)              # ex: "Ficha do desenvolvimento"
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    colecao_wsid = db.Column(db.String(20), nullable=True)        # NULL = global (v1: sempre NULL)

    def __repr__(self):
        return f'<FluxogamaSubetapa wsid={self.wsid!r} nome={self.nome!r}>'
