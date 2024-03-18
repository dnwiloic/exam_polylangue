import datetime
import base64
from odoo import fields, models, api
from werkzeug import urls
from odoo.addons.payment import utils as payment_utils

import logging
logger = logging.getLogger(__name__)
class AccountMoveInherit(models.Model):
    _inherit = 'account.move'
    _description = 'Account Move Inherit'

    start_invoice_date = fields.Date(string='Date debut de facturation')
    end_invoice_date = fields.Date(string='Date fin de facturation')
    access_token = fields.Char(store=False, compute="_get_access_token")
    inscription_ids = fields.One2many('examen.inscription','invoice_id')

    def _get_mail_template(self):
        """
        :return: the correct mail template based on the current move type
        """
        if len(self.inscription_ids) > 0:
            return (
                'account.email_template_edi_credit_note'
                if all(move.move_type == 'out_refund' for move in self)
                else 'exam_polylangue.email_template_edi_invoice_exam_buy'
            )
        else: 
             return (
                'account.email_template_edi_credit_note'
                if all(move.move_type == 'out_refund' for move in self)
                else 'account.email_template_edi_invoice'
            )
    
    def _get_access_token(self):
        self.ensure_one()
        self.access_token = payment_utils.generate_access_token(
            self.partner_id.id, self.amount_residual, self.currency_id.id
        )
        
    def generate_payment_link(self):
        self.ensure_one()
       
        link = ('%s/payment/pay?reference=%s&amount=%s&currency_id=%s'
                '&partner_id=%s&access_token=%s&invoice_id=%s') % (
                    self.get_base_url(),
                    urls.url_quote_plus(self.name),
                    self.amount_total,
                    self.currency_id.id,
                    self.partner_id.id,
                    self.access_token,
                    self.id
        )
        if self.company_id:
            link += '&company_id=%s' % self.company_id.id
        return link

    def send_invoice_payment_reminder(self):
        
        invoices_due = self.env['account.move'].search([('state','=','posted'),('move_type','=','out_invoice'),('payment_state','=','not_paid'),('invoice_date_due', '<', fields.Date.today())])
        
        today = datetime.date.today()
        
        for invoice in invoices_due:
            try:
                day = (today - invoice.invoice_date_due).days
                # Date echeance passé de 2jours
                if day == 2:
                    followup = self.env['followup.line'].search([('delay','=',2),('email_template_id','!=',False)], limit=1)
                # Date echeance passé de 8jours
                elif day == 8:
                    followup = self.env['followup.line'].search([('delay','=',8),('email_template_id','!=',False)], limit=1)
                # Date echeance passé de 14jours
                elif day == 14:
                    followup = self.env['followup.line'].search([('delay','=',14),('email_template_id','!=',False)], limit=1)
                else:
                    followup = False
                
                if followup is not False and followup.email_template_id:
                    template_id = followup.email_template_id
                    
                    # We can generate a pdf report and to convert it into binary type to create an attachment by,
                    invoice_report = self.env.ref('account.account_invoices')
                    data_record = base64.b64encode(self.env['ir.actions.report'].sudo()._render_qweb_pdf(invoice_report, [invoice.id], data=None)[0])
                    
                    # Now we can create the attachment,
                    ir_values = {
                        'name': 'Invoice ' + invoice.name,
                        'type': 'binary',
                        'datas': data_record,
                        'store_fname': data_record,
                        'mimetype': 'application/pdf',
                        'res_model': 'account.move',
                    }
            
                    invoice_report_attachment_id = self.env['ir.attachment'].sudo().create(ir_values)
                    
                    #  we are going to add this attachment to our email template by,
                    template_id.attachment_ids = [(4, invoice_report_attachment_id.id)]
                    
                    email_values = {
                        'email_to': invoice.partner_id.email
                    }
                    template_id.with_context(partner=invoice.partner_id,
                                                    inv=invoice).send_mail(invoice.id,email_values=email_values, force_send=True)
                    
                    # Delete attached file from template
                    # After sending the mail, we can remove the attachment from our mail template by using the code,
                    template_id.attachment_ids = [(5, 0, 0)]
                    self.env.cr.commit()
                
            except Exception as e:
                _logger.error("Error sending email: %s", e)
                continue