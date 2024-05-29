from odoo import fields, models, api,_
from datetime import datetime, timedelta


class Session(models.Model):
    _name = 'examen.session'
    _description = "Session d'examen"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    SESSION_STATES = [
        ('open','Ouvert'),
        ('close','Complet')
    ]

    def get_responsable_list(self):
        ids= self.env['res.groups'].sudo().search([("name","=","Responsable Agence")]).users.ids
        return ids
    
    responsable_ids = fields.Many2many(
        comodel_name="res.users", 
        relation='responsable_ids_rel',
        string='Responsables',
        domain=lambda self: [('id', 'in', self.env['res.users'].search([('groups_id.name', '=', 'Responsable Agence')]).ids)],
    )
    branch_ids = fields.Many2many(
        comodel_name="res.branch", 
        string="Branches", 
        related='responsable_id.branch_ids',
        relation="session_branch_rel", 
        column1="sessions", 
        column2="branchs"
    )

    name = fields.Char("Libelé")
    date = fields.Date("Date de l'examen", required=True, tracking=True)
    time = fields.Float(string='Heure Examen', default="10.0", required=True, tracking=True)
    min_cand = fields.Integer("Nombre minimun de candidat", 
                              default= lambda self: self.env['ir.config_parameter'].sudo().get_param("exam_polylangue.default_min_cand"), 
                              required=True)
    max_cand = fields.Integer("Nombre maximun de candidat",
                              default= lambda self: self.env['ir.config_parameter'].sudo().get_param("exam_polylangue.default_max_cand"),
                              required=True)

    responsable_id = fields.Many2one(comodel_name="res.users",string="Responsable", required=True,
                                     domain= lambda self: f"[('id', 'in', {self.get_responsable_list()})]")
    
    exam_center_id = fields.Many2one(comodel_name="res.branch", string="Lieu de l'examen", required=True)
    examen_id = fields.Many2one("product.product",required=True)
    inscription_ids = fields.One2many(comodel_name='examen.inscription', inverse_name='session_id', default=False)

    status = fields.Selection(SESSION_STATES, default="open", store=True, compute="_compute_nbr_inscription",
                              tracking=True)
    nbr_cand = fields.Integer("Nombre d'inscriptions", compute="_compute_nbr_inscription", store=True, default=0)
    
    last_inscription_day = fields.Date("Inscription Date line", store=True ,compute="_compute_last_inscription_day")
    # candidat liee a la session
    # cand_edof = fields.One2many(comodel_name="edof.registration.folder", inverse_name='exam_session_id')
    # cand_hcpf = fields.One2many(comodel_name="gestion.formation.dossier", inverse_name='exam_session_id')
    # candidats dont l'incription est valide
    participant_edof = fields.One2many("edof.registration.folder", inverse_name="exam_session_id")
    participant_archive_edof = fields.One2many(comodel_name='edof.data.archive', inverse_name="exam_session_id")
    
    
    participant_hors_cpf = fields.One2many("gestion.formation.dossier", inverse_name="exam_session_id")
    # invoice_ids = fields.

    invoice_ids = fields.One2many('account.move','session_id','Factures')
    invoice_count = fields.Integer(
        string='Invoice Count', readonly=True, default=0, compute='_compute_invoice_count')
    comments = fields.Text(
        string="Commentaires", 
        store=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            exam_center_id = self.env['res.branch'].search([('id','=',vals['exam_center_id'])])
            vals['name'] = f"SESSION - {exam_center_id.name} - {vals['date']}"
        
        return super(Session, self).create(vals_list)
    
    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for record in self:
            record.invoice_count = len(record.invoice_ids)
            
    @api.depends('date')
    def _compute_last_inscription_day(self):
        min_interval = int(self.env['ir.config_parameter'].sudo().get_param("exam_polylangue.minimal_day_before_inscription"))
        for rec in self:
            rec.last_inscription_day = rec.date - timedelta(days = min_interval)


    # Définir des contraintes
    @api.constrains('date')
    def _check_future_date(self):
        for record in self:
            current_date = datetime.now().date()
            if not record.date or  record.date < current_date:
                raise models.ValidationError(f"Vous ne pouvez pa programmer un examen dans le passé.")
                
            min_interval = int(self.env['ir.config_parameter'].sudo().get_param("exam_polylangue.minimal_day_before_inscription"))
            last_date = current_date - timedelta(days=min_interval)
            if  current_date > last_date:
                return {'warning':{
                    "title": "Date non appropriée",
                    "message": "Vous ne pouriez pas creer des inscriptions a cette session car le nombre de jour entre la date d'aujourd'hui et la date de l'examen est inferieur au delay necessaire a la creation des inscriptions"
                }}
    
    @api.constrains('responsable_id')
    def _check_default_branch(self):
        for rec in self:
            if not rec.responsable_id or not rec.responsable_id.branch_id:
                raise models.ValidationError(_("Ce responsable n'a pas de branche par defaut cela pourrais pauser problème lors de l'inscription"))

    @api.constrains('time')
    def _check_time(self):
        for record in self:
            if record.time < 0 or record.time >= 24.0:
                raise models.ValidationError(f"Horaire invalide")



    @api.onchange('date','responsable_id','examen_id')
    def _on_session_attr_change(self):
        if self.date and self.responsable_id and self.examen_id:
            other_session = self.env['examen.session'].sudo().search([('date','=',self.date),('responsable_id','=',self.responsable_id.id),('examen_id','=',self.examen_id.id)])
            if other_session:
                raise models.ValidationError(f"Une session d'examen de '{self.examen_id.name}' a déjà été programmé pour '{self.responsable_id.name}' en date du '{self.date}' ")

    @api.depends('inscription_ids')
    def _compute_status(self):
        for rec in self:
            if rec.get_nbr_inscription() == rec.max_cand:
                rec.status = 'close'

    @api.depends('inscription_ids','inscription_ids.status', 'inscription_ids.participant_edof', 'inscription_ids.participant_hors_cpf')
    def _compute_nbr_inscription(self):
        for rec in self:
            rec.nbr_cand = rec.get_nbr_inscription()
            if rec.nbr_cand >= rec.max_cand:
                rec.status = 'close'
            else:
                rec.status = 'open'


    def get_nbr_inscription(self):
        self.ensure_one()
        nbr_edof = 0
        nbr_cpf = 0
        inscription_ids = self.env['examen.inscription'].sudo().search([('session_id','=',self.id),('status','!=','cancel')])
        for elt in inscription_ids:
            nbr_edof = nbr_edof + len(elt.participant_edof)
            nbr_cpf = nbr_cpf + len(elt.participant_hors_cpf)

        return nbr_edof + nbr_cpf
    

    # def write(self, vals):
    #     if not vals:
    #         return True
        
    #     for move in self:
    #         if 'participant_edof' in vals:
    #             for inc in move.inscription_ids:
    #                 for p in inc.participant_edof:
    #                     if p.id in vals['participant_edof'][-1][-1] and p.status != 'EXAM_SCHEDULED':
    #                         p.sudo().write({
    #                             'status': 'EXAM_SCHEDULED'
    #                         })
    #                     elif p.id not in vals['participant_edof'][-1][-1] and p.status == 'EXAM_SCHEDULED':
    #                         p.sudo().write({
    #                             'status': 'EXAM_TO_CONFIRM'
    #                         })
            
    #         if 'participant_hors_cpf' in vals:
    #             for inc in move.inscription_ids:
    #                 for p in inc.participant_hors_cpf:
    #                     if p.id in vals['participant_hors_cpf'][-1][-1] and p.status != 'exam_scheduled':
    #                         p.sudo().write({
    #                             'status': 'exam_scheduled'
    #                         })
    #                     elif  p.id not in vals['participant_hors_cpf'][-1][-1] and p.status == 'exam_scheduled':
    #                         p.sudo().write({
    #                             'status': 'exam_to_confirm'
    #                         })

    #     return super().write(vals)


    def action_semd_convocation_mail(self):
        message = "<strong>Convocation envoyé à:</strong> <ul>"
        for rec in self:
            for p in rec.participant_edof:
                if p.status_exam == 'exam_sheduled':
                    p.send_exam_convocation()
                    message = f"{message} <li> <a ssss href='#id={p.id}&model=edof.registration.folder'><span>{p.attendee_first_name} {p.attendee_last_name}</span></a> </li>"
            for p in rec.participant_hors_cpf:
                if p.status_exam == 'exam_sheduled':
                    p.send_exam_convocation()
                    message = f"{message} <li><a  href='#id={p.id}&model=gestion.formation.dossier'><span>{p.first_name} {p.last_name}</span></a> </li>"
            message = f"{message} </ul>"
            self.message_post(body=message,
                              subject="Convocation a l'examen")

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'name': 'Invoices',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'tree',
            'views': [(False, 'tree'),(False, 'form')],
            'domain': [('id', 'in', self.invoice_ids.ids)],
            'target': 'current',
        }

