from odoo import fields, models, api, _
from datetime import datetime


class inscription(models.Model):
    _name = 'examen.inscription'
    _description = "Inscriptions aux examens"

    STATUS = [
        ('draft', 'Brouillon'),
        ('confirm', 'Confirmé'),
        ('paid', 'Payé'),
        ('cancel', 'Annulé')
    ]

    PAYMENT_STATE_SELECTION = [
        ('not_paid', 'Non payé'),
        ('in_payment', 'En cour de  Paiement'),
        ('paid', 'Payé'),
        ('partial', 'Partielement payé'),
        ('reversed', 'Reversé'),
        ('invoicing_legacy', "Héritage de l'application de facturation"),
]

    session_id = fields.Many2one("examen.session", required=True)
    participant_edof = fields.Many2many("edof.registration.folder", relation='inscription_participant_hors_cpf_rel')
    participant_hors_cpf = fields.Many2many("gestion.formation.dossier", relation='inscription_participant_edof_rel')
    branch_id = fields.Many2one("res.branch", string="Agence", compute="_compute_branch", store=True)
    status = fields.Selection(selection=STATUS, compute="_compute_status", string='Etat', default='draft', store=True)
    # status_payment = fields.Selection(selection=STATUS, compute="_compute_status", string='Etat', default='draft', store=True)
    invoice_id = fields.Many2one('account.move', required=False, default=None)
    status_paiment = fields.Selection(PAYMENT_STATE_SELECTION,readonly=True, compute="_compute_payment_state", store=True, default="not_paid")       

    def _compute_nbr_insciption(self):
        self.ensure_one()
        return len(self.participant_edof) + len(self.participant_hors_cpf)
    
    def get_nbr_inscription_to_session(self):
        self.ensure_one()
        return self.session_id.get_nbr_inscription()

    @api.depends('session_id')
    def _compute_branch(self):
        for record in self:
            if record.session_id:
                record.branch_id = record.session_id.branch_id
            else:
                record.branch_id = None
            

    @api.constrains('participant_edof', 'participant_hors_cpf')
    def _check_participant_limits(self):
        for record in self:
            min = record.session_id.min_cand
            max = record.session_id.max_cand
            nbr_cand = record.get_nbr_inscription_to_session()
            if record._compute_nbr_insciption() <= 0:
                raise models.ValidationError(f"Une inscription doit contenir au moins 1 candidat(e)")
            if nbr_cand > max:
                raise models.ValidationError(f"Vous devez inscrire au maximun {max} candidat(s) a cette session. \n Il reste {max - (nbr_cand - record._compute_nbr_insciption()) } place(s) ")
            if nbr_cand < min:
                raise models.ValidationError(f"Vous devez inscrire au minimum {min} candidat(s) a cette session")
            
        return True

    @api.depends('invoice_id.payment_state')
    def _compute_status(self):
        for record in self:
            if record.invoice_id and record.invoice_id.payment_state == 'paid':
                record.status = 'paid'

                for person in record.participant_edof:
                    print(f"=========={record.session_id}")
                    print(f"=========={person}")
                    person.sudo().write({
                        'exam_date': record.session_id.date,
                        'time': record.session_id.time,
                        'exam_center_id': record.branch_id.id,
                        'status': 'EXAM_TO_CONFIRM',
                        'exam_session_id': record.session_id.id
                    })

                for person in record.participant_hors_cpf:
                    person.sudo().write({
                        'exam_date': record.session_id.date,
                        'time': record.session_id.time,
                        'exam_center_id': record.branch_id.id,
                        'status': 'exam_to_confirm',
                        'exam_session_id': record.session_id.id
                    })

               


    def _get_default_journal(self):
        self.ensure_one()
        journal = self.env['account.journal'].search([('code','=',"INS_E"), ('type','=','sale'), ('company_id','=',self.env.company.id)])
        if not journal:
            journal = self.env['account.journal'].create({
                'name': "Inscription examen",
                'code': "INS_E",
                'type': "sale",
                'company_id': self.env.company.id
            })

        return journal
    
    def _get_penality_product(self):
        self.ensure_one()
        date_difference = self.session_id.date - datetime.today().date()
        days_difference = date_difference.days
        penality_product = self.env['product.product'].sudo().search([
            ('is_pass','=',True),
             ('penality_limit','>=',days_difference) ], order="penality_limit asc", limit=1)
        
        return penality_product


    def _compute_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            invoice_data = {
                'partner_id': self.branch_id.company_id.partner_id.id, 
                'branch_id': self.branch_id.id,
                'move_type': 'out_invoice',
                'invoice_date':fields.Date.today(),
                'journal_id': self._get_default_journal().id
            }
            try :
                self.invoice_id = self.env['account.move'].create(invoice_data)
            except Exception as e:
                simalars_partner = self.env['res.partner'].sudo().search([
                    ('name','=',self.branch_id.company_id.partner_id.name),
                    ('id','!=',self.branch_id.company_id.partner_id.id),
                    ('is_company','=',True)])
                for partner in simalars_partner:
                    invoice_data['partner_id'] = partner.id
                    try :
                        self.invoice_id = self.env['account.move'].create(invoice_data)
                        break
                    except :
                        pass
                    raise e
        else :
            for line in self.invoice_id.line_ids:
                line.unlink()    

        # create new product line
        self.env['account.move.line'].create({
                'move_id': self.invoice_id.id,
                'product_id': self.session_id.examen_id.id,
                'name': self._compute_invoice_description(),
                'quantity': self._compute_nbr_insciption(), 
                # 'account_id': insc.session_id.examen_id.account_id.id, 
            }
        )

        # check and add penality
        pass_product = self._get_penality_product()
        if pass_product :
            self.env['account.move.line'].create({
                'move_id': self.invoice_id.id,
                'product_id': pass_product.id,
                'name': f"Pénalité pour une inscription éffectué durant les {pass_product.penality_limit} jours précédant la date de l'examen",
                'quantity': self._compute_nbr_insciption(), 
                # 'account_id': insc.session_id.examen_id.account_id.id, 
            })

       

    def _post_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise models.UserError(_('Aucune facture sur cet inscription'))
        self.invoice_id.sudo().action_post()
        action = self.invoice_id.with_context(discard_logo_check=True).sudo().action_invoice_sent()
        action_context = action['context']

        self.invoice_id.with_context(**action_context).message_post_with_template(action_context.get('default_template_id'))


    def button_confirm(self, confirm=False):
        self.ensure_one()
        if self._check_participant_limits() and self.branch_id and self.branch_id.company_id:
            self._compute_invoice()
            message = ""
            for line in self.invoice_id.line_ids:
                if line.product_id.is_pass:
                    message = f"""En raison d'une inscription tardive a cette session d'examen, une pénalité de {line.product_id.list_price} {self.invoice_id.currency_id.name} par candidats sera facturé
                    Voulez-vous vraiment continuer ?"""
            # if confirm:
            return self.action_confirm() 
            # return {
            #     'type': 'ir.actions.act_window',
            #     'res_model': 'ir.actions.act_window',
            #     'name': _('Confirmation'),
            #     'view_mode': 'form',
            #     'target': 'new',
            #     'context': {
            #         'default_name': _(message),
            #         'default_type': 'ir.actions.act_window',
            #         'default_res_model': 'votre.model',
            #         'default_res_id': self.id,
            #         'default_method': 'action_confirm',
            #     }
            # }

    def action_confirm(self):
        for insc in self:
            if not insc.invoice_id:
                return False
            insc._post_invoice()
            insc.status='confirm'
                

    def button_cancel(self):
        for insc in self:
            insc.status='cancel'
            if insc.invoice_id:
                insc.invoice_id.button_cancel()
                insc.invoice_id.unlink()

    def action_view_invoice(self):
        self.ensure_one()
        # action = self.env['ir.actions.actions']._for_xml_id('account.action_move_out_invoice_type')
        if self.invoice_id:
            action = self.env['ir.actions.actions']._for_xml_id('account.action_move_out_invoice_type')
            form_view = [(self.env.ref('account.view_move_form').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + [(state,view) for state,view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = self.invoice_id.id
            return action
    

    def _compute_invoice_description(self):
        self.ensure_one()
        description = f"{self.session_id.examen_id.name}"
        if len(self.participant_edof) > 0:
            description = f"{description} \n  --- EDOF ---"
            for person in self.participant_edof:
                description = f"""{description}
                {person.attendee_last_name} {person.attendee_first_name} {person.folder_number}"""   

        if len(self.participant_hors_cpf) > 0:
            description = f"{description} \n   --- Hors CPF ---"
            for person in self.participant_hors_cpf:
                description = f"""{description}
                {person.last_name} {person.first_name} {person.number}"""   

        return description
    
    @api.depends('invoice_id.payment_state')
    def _compute_payment_state(self):
        for record in self:
            record.status_paiment = record.invoice_id.payment_state