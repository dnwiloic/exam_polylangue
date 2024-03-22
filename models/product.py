from odoo import api, fields, models, tools, _


class ProductProduct(models.Model):
    _inherit = "product.template"

    is_exam = fields.Boolean(string="Est Un Examen ?", default=False)
    is_pass = fields.Boolean(string="Est Un Pass ?",
                default=False,
                help="Coché dans le cas ou ce produit sert uniquement a pénaliser les inscriptions tardives")
    penality_limit = fields.Float("Limite de pénalité avant l'examen (en jours)",
                help="Nombre de jour précédant la session d'examen durant lequel l'achat d'une inscription entrainera l'achat de ce produit")
    

    @api.constrains('penality_limit')
    def _check_penality_limit(self):
        for record in self:
            if record.is_pass and record.penality_limit <= 0:
                raise models.ValidationError("Limite de pénalité doit être superieur a 0 jours.")    


    