# -*- coding: utf-8 -*-

import base64
import json
import os
import re
import fitz
import requests
from datetime import datetime
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ONSCCVImport(models.TransientModel):
    _name = 'onsc.import.cv'
    _description = 'CV importar'

    name_file = fields.Char(string="Nombre")
    file = fields.Binary(string="Archivo CV")

    def import_cv(self):
        print('Importar cv')


class ONSCCVDigitalImport(models.Model):
    _inherit = 'onsc.cv.digital'
    _description = 'Currículum digital importar'

    name_file_import = fields.Char(string="Importar CV")
    file_import = fields.Binary(string="Importar CV")

    @api.onchange('file_import', 'name_file_import')
    def onchange_import_cv(self):
        if self.file_import and self.name_file_import:
            try:
                api_url = "http://172.16.40.153:8000/procesar_cv"
                API_TOKEN = "123456"
                model_option = "Mistral-Free"
                # headers = {"Authorization": API_TOKEN}
                headers = {"Authorization": API_TOKEN, "Modelo": model_option}
                file_import = base64.b64decode(self.file_import)
                files = {
                    'file': (self.name_file_import, file_import)
                }
                # Foto
                ext = os.path.splitext(self.name_file_import)[1].lower()
                if ext == ".pdf":
                    img_bytes = self.extraer_imagen_cv_desde_pdf(file_import)
                    if img_bytes:
                        self.image_1920 = base64.b64encode(img_bytes)
                # Json
                response = requests.post(api_url, files=files, headers=headers)

                if response.status_code != 200:
                    raise UserError("Errores: %s" % response.status_code)
                respuesta = response.json()
                data = json.loads(respuesta)
                personal = data.get('personal_info', {}) or {}
                address = data.get('address', {}) or {}
                documents = data.get('documents', {}) or {}

                self.email = personal.get('email')

                def limpiar_prefijo_uy(numero):
                    if numero:
                        numero = re.sub(r'^(\+598|00598)\s*', '', numero)
                        return numero.replace(' ', '')
                    return ''

                self.personal_phone = limpiar_prefijo_uy(personal.get('phone'))
                self.mobile_phone = limpiar_prefijo_uy(personal.get('mobile_phone'))
                self.cv_birthdate = personal.get('birth_date', {})
                self.user_linkedIn = personal.get('linkedin', {})
                self.professional_resume = personal.get('summary', {})                
                self.cv_emissor_country_id = self.env['res.country'].search(
                    [('name', 'ilike', personal.get('birth_country', '')[:5])],
                    limit=1)

                self.uy_citizenship = 'Natural' if personal.get('nationality') == 'Uruguaya' else 'extranjero'

                if personal.get('marital_status'):
                    estado_json = personal.get('marital_status', '').strip().lower()
                    estados = self.env['onsc.cv.status.civil'].search([('name', 'ilike', estado_json[:4])])
                    self.marital_status_id = estados.id
                if personal.get('birth_country'):
                    country = self.env['res.country'].search([('name', 'ilike', personal['birth_country'][:5])],
                                                             limit=1)
                    self.country_of_birth_id = country.id

                gender = personal.get('gender')
                gender_rec = self.env['onsc.cv.gender'].search([('name', 'ilike', gender)], limit=1)
                self.cv_gender_id = gender_rec.id
                self.cv_gender2 = gender if gender_rec.name.lower() == 'otro' else ''
                self.is_cv_gender_option_other_enable = gender_rec.name.lower() == 'otro'

                ethnic = personal.get('ethnicity', {}) or {}
                race_ids = self.env['onsc.cv.race'].search([('name', 'ilike', ethnic[:4])])
                self.cv_race_ids = [(6, 0, race_ids.ids)]
                self.cv_first_race_id = race_ids[0].id if race_ids else False
                self.is_multiple_cv_race_selected = len(race_ids) > 1
                country_id = self.env['res.country'].search([('name', 'ilike', address.get('country', ''))],
                                                                 limit=1)
                self.country_id  =country_id.id
                cv_address_state= self.env['res.country.state'].search(
                    [('name', 'ilike', address.get('city', '')), ('country_id', '=', country_id.id)],
                    limit=1)
                self.cv_address_state_id = cv_address_state.id
                cv_address_location= self.env['onsc.cv.location'].search(
                    [('name', 'ilike', personal.get('location')[:4]),('state_id','=',cv_address_state.id)], limit=1)
                self.cv_address_location_id = cv_address_location.id
                street = address.get('street') or ''
                self.cv_address_street = street
                self.cv_address_apto = street.split('Apto')[-1].strip() if 'Apto' in street else ''
                self.cv_address_place = address.get('city')
                self.cv_address_zip = address.get('postal_code')
                calle = self.env['onsc.cv.street'].search([('street', 'ilike', address.get('street', '')[:5])],
                                                          limit=1).id
                self.cv_address_street_id = calle
                match = re.search(r'\b\d+\b', street)
                number = match.group(0) if match else None
                self.cv_address_nro_door = str(number)
                if not calle:
                    self.cv_address_amplification = address.get('street')
                self.cv_address_block = address.get('neighborhood')

                self.cv_document_type_id = 6
                identity_card = data.get('identity_card')
                self.cv_nro_doc = identity_card.get('number')
                expiry_date_str = identity_card.get('expiry_date')
                if identity_card and expiry_date_str != 'YYYY-MM-DD':
                    self.cv_expiration_date = expiry_date_str
                else:
                    self.cv_expiration_date = False

                cred = data.get('civic_credential', '') or {}
                self.crendencial_serie = cred.get('number')[:3] if cred.get('number') else ''
                self.credential_number = cred.get('number')[4:] if cred.get('number') else ''
                self.is_civical_credential_populated = bool(self.crendencial_serie and self.credential_number)

                self.is_driver_license = bool(data.get('driving_license'))
                # self.drivers_license_ids = [
                #     (0, 0, {
                #         'category_id': self.env['onsc.cv.license.category'].search([('name', '=', lic['category'])], limit=1).id,
                #         'validation_date': lic['expiry_date']
                #     }) for lic in documents.get('driving_license', [])
                # ]
                #
                # health = documents.get('health_card', {})
                # self.is_occupational_health_card = health.get('is_valid', False)
                # self.occupational_health_card_date = health.get('expiry_date') if self.is_occupational_health_card else False

                medical = data.get('medical_certificate', {})
                if medical:
                    self.is_medical_aptitude_certificate_status = medical.get('is_valid', False)
                    self.medical_aptitude_certificate_date = medical.get(
                        'expiry_date') if self.is_medical_aptitude_certificate_status else False

                basic_level_map = {
                    'Primaria': 'primary',
                    'Secundaria': 'secondary',
                }

                basic_formations = []
                for edu in data.get('education', []) or []:
                    degree_type = edu.get('degree_type')
                    start_date = datetime.strptime(f"{edu.get('start_year')}-01-01", "%Y-%m-%d").date()
                    end_date = datetime.strptime(f"{edu.get('end_year')}-12-31", "%Y-%m-%d").date()
                    if degree_type in basic_level_map:
                        institution = self.env['onsc.cv.institution'].search(
                            [('name', 'ilike', edu.get('institution'))], limit=1)
                        basic_formations.append((0, 0, {
                            'basic_education_level': basic_level_map[degree_type],
                            'institution_id': institution.id,
                            'start_date': edu.get('start_year'),
                            'end_date': edu.get('end_year'),
                            # 'state': edu.get('status'),
                            'coursed_years': f"{edu.get('start_date', '')} - {edu.get('end_date', '')}",
                        }))
                self.basic_formation_ids = basic_formations
                #
                advanced_formation_ids = []
                self.advanced_formation_ids = False
                for edu in data.get('education', []) or []:
                    degree_type = edu.get('degree_type')
                    if degree_type in basic_level_map:
                        continue
                    study_level = self.env['onsc.cv.study.level'].search([('name', 'ilike', degree_type)], limit=1)
                    institution = self.env['onsc.cv.institution'].search([('name', 'ilike', edu.get('institution'))],
                                                                         limit=1)
                    start_date = datetime.strptime(f"{edu.get('start_year')}-01-01", "%Y-%m-%d").date()
                    end_date = datetime.strptime(f"{edu.get('end_year')}-12-31", "%Y-%m-%d").date()
                    thesis = edu.get('thesis', {}) or {}
                    advanced_formation_ids.append((0, 0, {
                        'advanced_study_level_id': study_level.id,
                        'institution_id': institution,
                        'start_date': start_date,
                        'end_date': end_date,
                        # 'state': edu.get('status'),
                        'issue_title_date': edu.get('graduation_date'),
                        'egress_date': end_date,
                        'is_require_thesis': bool(thesis),
                        'state_thesis': 'completed' if thesis else 'no_starting',
                        'title_thesis': thesis.get('title'),
                        'description_thesis': thesis.get('description'),
                        'final_note_thesis': thesis.get('final_grade'),
                        'max_note_thesis': 12.0 if thesis.get('final_grade') else 0,
                    }))
                self.advanced_formation_ids = advanced_formation_ids
                self.work_experience_ids = False
                self.work_experience_ids = [(0, 0, {
                    'company_name': job.get('company'),
                    'position': job.get('title'),
                    'start_date': job.get('start'),
                    'end_date': job.get('end'),
                    'description_tasks': job.get('description'),
                }) for job in data.get('experience', []) or []]
                self.course_ids = False
                self.course_ids = [(0, 0, {
                    'name': 'Curso',
                    'course_title': curso.get('title'),
                    'internal_course_name': curso.get('provider'),
                    'hours_total': curso.get('hours'),
                    'start_date': curso.get('start_date'),
                    'end_date': curso.get('end_date'),
                }) for curso in data.get('courses', []) or []]

                self.volunteering_ids = False
                self.volunteering_ids = [(0, 0, {
                    'company_name': vol.get('organization'),
                    'start_date': vol.get('start'),
                    'end_date': vol.get('end'),
                    'position': vol.get('role'),
                }) for vol in data.get('volunteering', []) or []]

                level_map = {
                    'básico': 'd',
                    'intermedio': 'c',
                    'avanzado': 'b',
                    'nativo': 'a'
                }
                self.language_level_ids = False
                language_level_lines = []
                for lang in data.get('languages', []) or []:
                    language_name = lang.get('language', '')
                    language = self.env['onsc.cv.language'].search([('name', 'ilike', language_name)], limit=1)
                    if not language:
                        continue

                    spoken = level_map.get(lang.get('spoken', '').lower())
                    written = level_map.get(lang.get('written', '').lower())
                    read = level_map.get(lang.get('reading', '').lower())

                    if not (spoken and written and read):
                        continue
                    language_level_lines.append((0, 0, {
                        'language_id': language.id,
                        'spoken_level': spoken,
                        'write_level': written,
                        'read_level': read,
                    }))
                self.language_level_ids = language_level_lines
                #
                # disability = personal.get('disability', {}) or {}
                # self.situation_disability = 'si' if disability.get('is_disabled') else 'no'
                # self.people_disabilitie = 'si' if disability.get('is_disabled') else 'no'
                # self.certificate_date = disability.get('disability_certificate_date')
                # self.to_date = disability.get('disability_certificate_expiry')
                # # self.allow_content_public = 'si' if disability.get('is_disabled') else 'no'
                #
                # support = disability.get('support_needed', {}) or {}
                # support_tags = []
                # if support.get('vision'):
                #     tag = self.env['onsc.cv.type.support'].search([('name', 'ilike', 'visión')], limit=1)
                #     if tag:
                #         support_tags.append(tag.id)
                # if support.get('software_support'):
                #     tag = self.env['onsc.cv.type.support'].search([('name', 'ilike', 'software')], limit=1)
                #     if tag:
                #         support_tags.append(tag.id)
                #
                # self.need_other_support = support.get('other_support')
                # self.is_need_other_support = bool(self.need_other_support)
                # self.type_support_ids = [(6, 0, support_tags)]
                #
                if self.situation_disability != 'si':
                    self.see = False
                    self.walk = False
                    self.realize = False
                    self.interaction = False
                    self.hear = False
                    self.speak = False
                    self.lear = False
                self.other_relevant_information_ids = False
                self.other_relevant_information_ids = [
                    (0, 0, {
                        'theme': section.get('title'),
                        'description': section.get('content'),
                    }) for section in data.get('extra_sections', []) or []
                ]

            except Exception as e:
                raise ValidationError(f"Error al procesar el archivo JSON: {e}")

    def extraer_imagen_cv_desde_pdf(self, pdf_file_bytes: bytes, min_size=(100, 100)):
        try:
            doc = fitz.open("pdf", pdf_file_bytes)
            for page_index in range(min(1, len(doc))):  # Solo primera página
                for img in doc.get_page_images(page_index):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    width = base_image["width"]
                    height = base_image["height"]
                    if width >= min_size[0] and height >= min_size[1]:
                        return image_bytes
        except Exception as e:
            raise ValidationError(f"Error usando PyMuPDF: {str(e)}")
        return None
