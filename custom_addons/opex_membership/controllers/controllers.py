# from odoo import http


# class GicPortal(http.Controller):
#     @http.route('/gic_portal/gic_portal', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/gic_portal/gic_portal/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('gic_portal.listing', {
#             'root': '/gic_portal/gic_portal',
#             'objects': http.request.env['gic_portal.gic_portal'].search([]),
#         })

#     @http.route('/gic_portal/gic_portal/objects/<model("gic_portal.gic_portal"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('gic_portal.object', {
#             'object': obj
#         })

