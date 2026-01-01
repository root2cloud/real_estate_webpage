# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError
import base64
import logging

_logger = logging.getLogger(__name__)


class AgentPortalController(http.Controller):
    """Secure Agent Portal - Similar to Family Members"""

    def _get_logged_in_agent(self):
        """Get agent for current logged-in user"""
        if not request.env.user or request.env.user._is_public():
            return False

        # Search for agent linked to this user
        agent = request.env['real.estate.agent'].search([
            ('user_id', '=', request.env.user.id),
            ('is_active', '=', True)
        ], limit=1)

        return agent

    @http.route(['/my/agent/dashboard'], type='http', auth='user', website=True)
    def agent_dashboard(self, **kw):
        """Main dashboard - like family members portal"""
        agent = self._get_logged_in_agent()

        if not agent:
            return request.render('real_estate_management.agent_no_access')

        # Get only THIS agent's properties
        properties = request.env['property.property'].search([
            ('agent_id', '=', agent.id)
        ], order='create_date desc')

        # Stats
        stats = {
            'total_properties': len(properties),
            'published': len(properties.filtered('is_published')),
            'pending': len(properties.filtered(lambda p: not p.is_published)),
            'total_views': sum(properties.mapped('views')),
        }

        return request.render('real_estate_management.agent_portal_dashboard', {
            'agent': agent,
            'properties': properties[:10],  # Show recent 10
            'stats': stats,
        })

    @http.route(['/my/agent/profile'], type='http', auth='user', website=True)
    def agent_profile(self, **kw):
        """View own profile"""
        agent = self._get_logged_in_agent()

        if not agent:
            return request.redirect('/my')

        return request.render('real_estate_management.agent_portal_profile', {
            'agent': agent,
        })

    @http.route(['/my/agent/properties'], type='http', auth='user', website=True)
    def agent_my_properties(self, **kw):
        """List of MY properties only"""
        agent = self._get_logged_in_agent()

        if not agent:
            return request.redirect('/my')

        properties = request.env['property.property'].search([
            ('agent_id', '=', agent.id)
        ], order='create_date desc')

        return request.render('real_estate_management.agent_portal_my_properties', {
            'agent': agent,
            'properties': properties,
            'success': kw.get('success'),
        })

    @http.route(['/my/agent/property/add'], type='http', auth='user', website=True)
    def agent_add_property_form(self, **kw):
        """Add property form - like registration form"""
        agent = self._get_logged_in_agent()

        if not agent:
            return request.redirect('/my')

        categories = request.env['property.category'].sudo().search([])

        return request.render('real_estate_management.agent_portal_add_property', {
            'agent': agent,
            'categories': categories,
            'error': kw.get('error'),
        })

    # @http.route(['/my/agent/property/submit'], type='http', auth='user', website=True, csrf=False, methods=['POST'])
    # def agent_submit_property(self, **post):
    #     """Submit property"""
    #     agent = self._get_logged_in_agent()
    #
    #     if not agent:
    #         return request.redirect('/my')
    #
    #     try:
    #         # Get files
    #         main_image = request.httprequest.files.get('main_image')
    #         gallery_images = request.httprequest.files.getlist('gallery_images')
    #
    #         # Create property
    #         property_vals = {
    #             'name': post.get('property_name'),
    #             'property_type': post.get('property_type'),
    #             'price': float(post.get('price', 0)),
    #             'plot_area': float(post.get('plot_area', 0)),
    #             'bedrooms': int(post.get('bedrooms', 0)),
    #             'bathrooms': int(post.get('bathrooms', 0)),
    #             'city': post.get('city'),
    #             'zip_code': post.get('zip_code'),
    #             'street': post.get('street'),
    #             'address': post.get('address'),
    #             'description': post.get('description'),
    #             'short_description': post.get('short_description'),
    #             'agent_id': agent.id,  # Link to THIS agent
    #             'status': 'available',
    #             'is_published': False,  # Needs admin approval
    #             'contact_name': agent.name,
    #             'contact_email': agent.email,
    #             'contact_phone': agent.phone,
    #         }
    #
    #         if post.get('category_id'):
    #             property_vals['category_id'] = int(post.get('category_id'))
    #
    #         if main_image:
    #             property_vals['image'] = base64.b64encode(main_image.read())
    #
    #         property_obj = request.env['property.property'].create(property_vals)
    #
    #         # Gallery images
    #         for img in gallery_images:
    #             if img and img.filename:
    #                 request.env['property.gallery.image'].sudo().create({
    #                     'property_id': property_obj.id,
    #                     'image': base64.b64encode(img.read()),
    #                     'name': img.filename,
    #                 })
    #
    #         _logger.info(f"✅ Property submitted by {agent.name}: {property_obj.name}")
    #
    #         return request.redirect('/my/agent/properties?success=1')
    #
    #     except Exception as e:
    #         _logger.exception("Error submitting property")
    #         return request.redirect('/my/agent/property/add?error=1')

    @http.route(['/my/agent/property/submit'], type='http', auth='user', website=True, methods=['POST'])
    def agent_submit_property(self, **post):
        """Submit property with detailed error handling"""
        agent = self._get_logged_in_agent()

        if not agent:
            return request.redirect('/my')

        try:
            _logger.info(f"=== Starting property submission for agent: {agent.name} ===")

            # Get uploaded files
            files = request.httprequest.files
            main_image = files.get('main_image')
            gallery_images = files.getlist('gallery_images')

            _logger.info(f"POST data received: {list(post.keys())}")
            _logger.info(f"Files received: main_image={main_image is not None}, gallery_count={len(gallery_images)}")

            # Get state from form or use agent's state
            state_id = post.get('state_id')
            if state_id and state_id != '':
                try:
                    state_id = int(state_id)
                except (ValueError, TypeError):
                    state_id = agent.state_id.id if agent.state_id else False
            else:
                state_id = agent.state_id.id if agent.state_id else False

            # ⭐ BUILD PROPERTY VALUES WITH ALL REQUIRED FIELDS
            property_vals = {
                # Basic required fields
                'name': post.get('property_name', '').strip() or 'Untitled Property',
                'agent_id': agent.id,
                'is_published': False,
                'status': 'available',

                # Location (required)
                'city': post.get('city', '').strip() or 'Not Specified',
                'state_id': state_id,
                'zip_code': post.get('zip_code', '').strip() or '000000',

                # Price & Area (required)
                'price': float(post.get('price', 0) or 0),
                'plot_area': float(post.get('plot_area', 100) or 100),

                # ⭐ REQUIRED FIELDS WITH DEFAULTS
                'facing_direction': 'east',  # Default value
                'road_width': 30.0,  # Default 30 feet
                'title_status': 'pending',  # Default status
                'seo_title': post.get('property_name', '').strip() or 'Property for Sale',
                'nearby_landmarks': post.get('address', '').strip() or 'Updated soon',

                # Contact info
                'contact_name': agent.name,
                'contact_email': agent.email,
                'contact_phone': agent.phone,
            }

            # Add optional fields if provided
            if post.get('property_type'):
                property_vals['property_type'] = post.get('property_type')

            if post.get('bedrooms'):
                try:
                    property_vals['bedrooms'] = int(post.get('bedrooms', 0))
                except (ValueError, AttributeError):
                    property_vals['bedrooms'] = 0

            if post.get('bathrooms'):
                try:
                    property_vals['bathrooms'] = int(post.get('bathrooms', 0))
                except (ValueError, AttributeError):
                    property_vals['bathrooms'] = 0

            if post.get('street'):
                property_vals['street'] = post.get('street').strip()

            if post.get('address'):
                property_vals['address'] = post.get('address').strip()

            if post.get('short_description'):
                property_vals['short_description'] = post.get('short_description').strip()

            if post.get('description'):
                property_vals['detailed_description'] = post.get('description').strip()

            # Category
            category_id = post.get('category_id')
            if category_id and category_id != '':
                try:
                    property_vals['category_id'] = int(category_id)
                except (ValueError, TypeError):
                    pass

            # Main image
            if main_image and hasattr(main_image, 'read'):
                try:
                    image_data = main_image.read()
                    if image_data:
                        property_vals['image'] = base64.b64encode(image_data)
                        _logger.info("Main image uploaded successfully")
                except Exception as img_err:
                    _logger.error(f"Image upload error: {img_err}")

            _logger.info(f"Creating property with values: {property_vals}")

            # Create property
            PropertyModel = request.env['property.property'].sudo()
            property_obj = PropertyModel.create(property_vals)

            _logger.info(f"✅ Property created successfully: ID={property_obj.id}, Name={property_obj.name}")

            # Handle gallery images
            if gallery_images:
                GalleryModel = request.env['property.gallery.image'].sudo()
                for idx, img_file in enumerate(gallery_images):
                    if img_file and hasattr(img_file, 'read') and img_file.filename:
                        try:
                            img_data = img_file.read()
                            if img_data:
                                GalleryModel.create({
                                    'property_id': property_obj.id,
                                    'image': base64.b64encode(img_data),
                                    'name': img_file.filename,
                                })
                                _logger.info(f"Gallery image {idx + 1} uploaded: {img_file.filename}")
                        except Exception as gal_err:
                            _logger.error(f"Gallery image {idx + 1} error: {gal_err}")

            _logger.info("=== Property submission completed successfully ===")

            return request.redirect('/my/agent/properties?success=1')

        except Exception as e:
            _logger.exception(f"❌ CRITICAL ERROR in property submission")
            _logger.error(f"Error type: {type(e).__name__}")
            _logger.error(f"Error message: {str(e)}")

            return request.redirect('/my/agent/property/add?error=1')

    @http.route(['/my/agent/property/<int:property_id>'], type='http', auth='user', website=True)
    def agent_property_detail(self, property_id, **kw):
        """View property - only if belongs to THIS agent"""
        agent = self._get_logged_in_agent()

        if not agent:
            return request.redirect('/my')

        property_obj = request.env['property.property'].browse(property_id)

        # Security: Check ownership
        if not property_obj.exists() or property_obj.agent_id != agent:
            return request.render('real_estate_management.agent_no_access', {
                'message': 'You do not have access to this property.'
            })

        return request.render('real_estate_management.agent_portal_property_detail', {
            'agent': agent,
            'property': property_obj,
        })

    @http.route(['/my/agent/property/update_status'], type='http', auth='user', methods=['POST'], csrf=True)
    def update_property_status(self, property_id=None, new_status=None, **kwargs):
        """Update property status - HTTP POST endpoint"""
        try:
            _logger.info(f"📝 Status update request: property_id={property_id}, new_status={new_status}")

            # Validate inputs
            if not property_id or not new_status:
                return request.make_json_response({
                    'success': False,
                    'message': 'Missing required parameters.'
                })

            # Get logged in agent
            agent = self._get_logged_in_agent()

            if not agent:
                return request.make_json_response({
                    'success': False,
                    'message': 'Agent not found. Please login again.'
                })

            # Get property and verify ownership
            property_obj = request.env['property.property'].sudo().search([
                ('id', '=', int(property_id)),
                ('agent_id', '=', agent.id)
            ], limit=1)

            if not property_obj:
                return request.make_json_response({
                    'success': False,
                    'message': 'Property not found or you do not have permission.'
                })

            # Validate status
            if new_status not in ['available', 'sold', 'rented']:
                return request.make_json_response({
                    'success': False,
                    'message': 'Invalid status value.'
                })

            # Update status
            old_status = property_obj.status
            property_obj.write({'status': new_status})

            _logger.info(f"✅ Property '{property_obj.name}' status: {old_status} → {new_status} (Agent: {agent.name})")

            return request.make_json_response({
                'success': True,
                'message': f'Status updated to "{new_status.upper()}" successfully!',
                'new_status': new_status
            })

        except Exception as e:
            _logger.exception(f"❌ Error updating status: {e}")
            return request.make_json_response({
                'success': False,
                'message': 'An error occurred. Please try again.'
            })

