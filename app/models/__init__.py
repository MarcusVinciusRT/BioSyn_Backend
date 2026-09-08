"""Models das 8 tabelas do DDL BioSyn.

O schema e a fonte da verdade: nao ha migrations. Sequences, atualizado_em e
auditoria sao responsabilidade do banco (triggers do DDL v2).
"""

from app.models.alerta_disparado import AlertaDisparado
from app.models.cargo import Cargo
from app.models.dashboard_config import DashboardConfig
from app.models.endereco import Endereco
from app.models.log_auditoria import LogAuditoria
from app.models.metrica import Metrica
from app.models.organizacao import Organizacao
from app.models.usuario import Usuario

__all__ = [
    "AlertaDisparado",
    "Cargo",
    "DashboardConfig",
    "Endereco",
    "LogAuditoria",
    "Metrica",
    "Organizacao",
    "Usuario",
]
