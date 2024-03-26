from odoo import fields, models, api, _
from datetime import datetime, timedelta


class inscription(models.Model):
    _name = 'examen.inscription'
    _description = "Inscriptions aux examens"

    STATUS = [
        ('draft', 'Brouillon'),
        ('confirm', 'Confirmé'),
        ('validate', 'Validé'),
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
    
    # @api.depends('participant_edof.exam_session_id')
    # def _compute_participant_edof(self):

    # @api.depends('participant_hors_cpf.exam_session_id')
    # def _compute_participant_hors_cpf(self):
    #     for rec in self:
    #         if rec.status in ['confirm','validate']

    def _check_required_info_for_inscription(self):
        self.ensure_one()
        for p in self.participant_edof:
            if not p.gender or not p.birth_day or not p.nationality or not p.maternal_langage \
                or not p.motivation or not p.n_cni_ts or not p.insciption_file :
                raise models.ValidationError(f"Les champs 'genre', 'data de naissance', 'pays de nationalité', 'motivation','N° de CNI/TS', 'langue maternelle' et 'fichier' sont requis pour inscrire un candidat.\
                                 \n Veuillez tous les renseigner chez {p.attendee_last_name} {p.attendee_first_name} et autres")
        
        for p in self.participant_hors_cpf:
            if not p.gender or not p.birth_day or not p.nationality or not not p.maternal_langage\
                or not p.motivation or not p.n_cni_ts or not p.insciption_file :
                raise models.ValidationError(f"Les champs 'genre', 'data de naissance', 'pays de nationalité', 'motivation','N° de CNI/TS', 'langue maternelle' et 'fichier' sont requis pour inscrire un candidat.\
                                 \n Veuillez tous les renseigner chez {p.first_name} {p.last_name} et autres")
        return True
    
    def _get_invoiced_company(self):
        if self.env['ir.config_parameter'].sudo().get_param("exam_polylangue.choose_session_accounting_comopany") == 'other':
            cmp_id = int(self.env['ir.config_parameter'].sudo().get_param("exam_polylangue.session_accounting_comopany"))
            return self.env['res.company'].sudo().search([('id','=',cmp_id)])
        else :
            return self.env.company

    def _should_be_invoiced(self):
        self.ensure_one()
        not_invoiced_company_id = self._get_invoiced_company().id
        if not_invoiced_company_id and not_invoiced_company_id == self.branch_id.company_id.id:
            return False

        return True
    
    def _validate_inscription(self):
        self.ensure_one()
        
        if not self._should_be_invoiced():
            if self.status != 'confirm' : return    
            self.status = 'validate'

        elif self.invoice_id and self.invoice_id.payment_state == 'paid':
            self.status = 'validate'
        else: 
            return

        for person in self.participant_edof:
            person.sudo().write({
                'exam_date': self.session_id.date,
                'time': self.session_id.time,
                'exam_center_id': self.branch_id.id,
                'status': 'EXAM_TO_CONFIRM',
                'exam_session_id': self.session_id.id
            })

        for person in self.participant_hors_cpf:
            person.sudo().write({
                'exam_date': self.session_id.date,
                'time': self.session_id.time,
                'exam_center_id': self.branch_id.id,
                'status': 'exam_to_confirm',
                'exam_session_id': self.session_id.id
            })


    @api.depends('invoice_id.payment_state')
    def _compute_status(self):
        for record in self:
           record._validate_inscription()
               


    def _get_default_journal(self):
        self.ensure_one()
        journal = self.env['account.journal'].sudo().search([('type','=','sale'), ('company_id','=',self._get_invoiced_company().id)], limit=1)
        if not journal:
            journal = self.env['account.journal'].sudo().create({
                'name': "Inscription examen",
                'code': "INS_E",
                'type': "sale",
                'company_id': self._get_invoiced_company().id
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
                self.invoice_id = self.env['account.move'].sudo().create(invoice_data)
            except Exception as e:
                simalars_partner = self.env['res.partner'].sudo().search([
                    ('name','=',self.branch_id.company_id.partner_id.name),
                    ('id','!=',self.branch_id.company_id.partner_id.id),
                    ('is_company','=',True)])
                for partner in simalars_partner:
                    invoice_data['partner_id'] = partner.id
                    try :
                        self.invoice_id = self.env['account.move'].sudo().create(invoice_data)
                        break
                    except :
                        pass
                    raise models.ValidationError("Impossible de creer la facture")
        # else :
            # for line in self.invoice_id.line_ids:
            #     line.sudo().unlink()    

        # create new product line
        self.env['account.move.line'].sudo().create({
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
            self.env['account.move.line'].sudo().create({
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

        self.invoice_id.with_context(**action_context).sudo().message_post_with_template(action_context.get('default_template_id'))


    def button_confirm(self, confirm=False):
        self.ensure_one()
        if self._check_participant_limits() and  self._check_required_info_for_inscription() and self.branch_id and self.branch_id.company_id:
            if self._should_be_invoiced():
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
            if self._should_be_invoiced():
                if not insc.invoice_id:
                    return False
                insc._post_invoice()
            insc.status='confirm'
            self._validate_inscription()
                

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

    