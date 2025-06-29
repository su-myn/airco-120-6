from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Contact, Unit
from utils.access_control import get_accessible_units_query

contacts_bp = Blueprint('contacts', __name__)

@contacts_bp.route('/contacts')
@login_required
def contacts():
    # Get all contacts for the current user's company
    user_company_id = current_user.company_id
    contacts_list = Contact.query.filter_by(company_id=user_company_id).all()

    # Get accessible units for filtering buildings
    units = get_accessible_units_query().all()

    # Extract unique building names from accessible units only
    buildings_set = set()
    for unit in units:
        if unit.building:
            buildings_set.add(unit.building)
    buildings_list = sorted(list(buildings_set))

    return render_template('contact.html', contacts=contacts_list, units=units, buildings_list=buildings_list)


@contacts_bp.route('/add_contact', methods=['POST'])
@login_required
def add_contact():
    if request.method == 'POST':
        try:
            full_name = request.form['full_name']
            role = request.form['role']
            phone = request.form.get('phone', '')

            # Handle custom building input
            building = request.form.get('building', '')
            custom_building = request.form.get('custom_building', '')

            if building == 'custom' and custom_building:
                building = custom_building

            favourite = 'favourite' in request.form
            notes = request.form.get('notes', '')

            # Create and add new contact
            new_contact = Contact(
                full_name=full_name,
                role=role,
                phone=phone,
                building=building,
                favourite=favourite,
                notes=notes,
                company_id=current_user.company_id,
                user_id=current_user.id
            )

            db.session.add(new_contact)
            db.session.commit()

            flash('Contact added successfully', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding contact: {str(e)}', 'danger')

        return redirect(url_for('contacts.contacts'))

    return redirect(url_for('contacts.contacts'))


@contacts_bp.route('/edit_contact/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_contact(id):
    contact = Contact.query.get_or_404(id)

    # Ensure the contact belongs to the user's company
    if contact.company_id != current_user.company_id:
        flash('You do not have permission to edit this contact', 'danger')
        return redirect(url_for('contacts.contacts'))

    if request.method == 'POST':
        contact.full_name = request.form['full_name']
        contact.role = request.form['role']
        contact.phone = request.form.get('phone', '')

        # Handle custom building input
        building = request.form.get('building', '')
        custom_building = request.form.get('custom_building', '')

        if building == 'custom' and custom_building:
            contact.building = custom_building
        else:
            contact.building = building

        contact.favourite = 'favourite' in request.form
        contact.notes = request.form.get('notes', '')

        db.session.commit()
        flash('Contact updated successfully', 'success')
        return redirect(url_for('contacts.contacts'))

    # Get unique building names from accessible units only
    units = get_accessible_units_query().all()
    buildings_set = set()
    buildings_list = []
    for unit in units:
        if unit.building and unit.building not in buildings_set:
            buildings_set.add(unit.building)
            buildings_list.append(unit.building)

    return render_template('edit_contact.html', contact=contact, buildings_list=buildings_list)


@contacts_bp.route('/delete_contact/<int:id>')
@login_required
def delete_contact(id):
    contact = Contact.query.get_or_404(id)

    # Ensure the contact belongs to the user's company
    if contact.company_id != current_user.company_id:
        flash('You do not have permission to delete this contact', 'danger')
        return redirect(url_for('contacts.contacts'))

    db.session.delete(contact)
    db.session.commit()

    flash('Contact deleted successfully', 'success')
    return redirect(url_for('contacts.contacts'))