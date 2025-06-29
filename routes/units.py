from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Unit, Company, Issue, BookingForm, ExpenseData, ExpenseRemark, Complaint, Repair, Replacement, CalendarSource
from utils.access_control import (
    get_accessible_units_query,
    check_unit_access,
    require_unit_access
)

units_bp = Blueprint('units', __name__)

@units_bp.route('/manage_units')
@login_required
def manage_units():
    # Redirect cleaners to cleaner dashboard
    if current_user.is_cleaner:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('cleaners.cleaner_dashboard'))

    # Get accessible units for current user using access control
    units = get_accessible_units_query().all()

    return render_template('manage_units.html', units=units)

@units_bp.route('/add_unit', methods=['GET', 'POST'])
@login_required
def add_unit():
    if request.method == 'POST':
        unit_number = request.form['unit_number']
        building = request.form['building']
        address = request.form.get('address')
        is_occupied = 'is_occupied' in request.form

        # Get values for all fields
        letterbox_code = request.form.get('letterbox_code') or None
        smartlock_code = request.form.get('smartlock_code') or None
        wifi_name = request.form.get('wifi_name') or None
        wifi_password = request.form.get('wifi_password') or None

        # Process numeric fields
        bedrooms = request.form.get('bedrooms') or None
        bathrooms = request.form.get('bathrooms') or None
        sq_ft = request.form.get('sq_ft') or None
        toilet_count = request.form.get('toilet_count') or None
        towel_count = request.form.get('towel_count') or None
        default_toilet_paper = request.form.get('default_toilet_paper') or None
        default_towel = request.form.get('default_towel') or None
        default_garbage_bag = request.form.get('default_garbage_bag') or None
        monthly_rent = request.form.get('monthly_rent') or None
        max_pax = request.form.get('max_pax') or None

        # Convert to appropriate types if not None
        if bedrooms:
            bedrooms = int(bedrooms)
        if bathrooms:
            bathrooms = float(bathrooms)
        if sq_ft:
            sq_ft = int(sq_ft)
        if toilet_count:
            toilet_count = int(toilet_count)
        if towel_count:
            towel_count = int(towel_count)
        if default_toilet_paper:
            default_toilet_paper = int(default_toilet_paper)
        if default_towel:
            default_towel = int(default_towel)
        if default_garbage_bag:
            default_garbage_bag = int(default_garbage_bag)
        if monthly_rent:
            monthly_rent = float(monthly_rent)
        if max_pax:
            max_pax = int(max_pax)

        # Get current user's company
        company_id = current_user.company_id
        company = Company.query.get(company_id)

        # Check if unit number already exists in this company only
        existing_unit = Unit.query.filter_by(unit_number=unit_number, company_id=company_id).first()
        if existing_unit:
            flash('This unit number already exists in your company', 'danger')
            return redirect(url_for('units.add_unit'))

        # Check if company has reached their unit limit (updated for new system)
        current_units_count = Unit.query.filter_by(company_id=company_id).count()
        max_units = company.max_units  # Use the flexible max_units field

        if current_units_count >= max_units:
            flash(
                f'Your company has reached the limit of {max_units} units. Please contact admin to increase your limit.',
                'danger')
            return redirect(url_for('units.manage_units'))

        # Create new unit with all fields
        new_unit = Unit(
            unit_number=unit_number,
            building=building,
            address=address,
            company_id=company_id,
            is_occupied=is_occupied,
            letterbox_code=letterbox_code,
            smartlock_code=smartlock_code,
            wifi_name=wifi_name,
            wifi_password=wifi_password,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            sq_ft=sq_ft,
            toilet_count=toilet_count,
            towel_count=towel_count,
            default_toilet_paper=default_toilet_paper,
            default_towel=default_towel,
            default_garbage_bag=default_garbage_bag,
            monthly_rent=monthly_rent,
            max_pax=max_pax
        )

        db.session.add(new_unit)
        db.session.commit()

        flash('Unit added successfully', 'success')
        return redirect(url_for('units.manage_units'))

    return render_template('add_unit_user.html')


@units_bp.route('/edit_unit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_unit(id):
    unit = Unit.query.get_or_404(id)

    # Check if the unit belongs to the user's company
    if unit.company_id != current_user.company_id:
        flash('You do not have permission to edit this unit', 'danger')
        return redirect(url_for('units.manage_units'))

    # Check if user can access this unit
    if not check_unit_access(id):
        flash('You do not have permission to edit this unit', 'danger')
        return redirect(url_for('units.manage_units'))

    # Rest of the function remains the same...
    if request.method == 'POST':
        unit.unit_number = request.form['unit_number']
        unit.building = request.form['building']
        unit.address = request.form.get('address')
        unit.is_occupied = 'is_occupied' in request.form

        # Update new fields (keep existing code)
        unit.letterbox_code = request.form.get('letterbox_code') or None
        unit.smartlock_code = request.form.get('smartlock_code') or None
        unit.wifi_name = request.form.get('wifi_name') or None
        unit.wifi_password = request.form.get('wifi_password') or None

        # Handle numeric fields (keep existing code for all numeric fields)
        bedrooms = request.form.get('bedrooms') or None
        if bedrooms:
            unit.bedrooms = int(bedrooms)
        else:
            unit.bedrooms = None

        bathrooms = request.form.get('bathrooms') or None
        if bathrooms:
            unit.bathrooms = float(bathrooms)
        else:
            unit.bathrooms = None

        sq_ft = request.form.get('sq_ft') or None
        if sq_ft:
            unit.sq_ft = int(sq_ft)
        else:
            unit.sq_ft = None

        toilet_count = request.form.get('toilet_count') or None
        if toilet_count:
            unit.toilet_count = int(toilet_count)
        else:
            unit.toilet_count = None

        towel_count = request.form.get('towel_count') or None
        if towel_count:
            unit.towel_count = int(towel_count)
        else:
            unit.towel_count = None

        default_toilet_paper = request.form.get('default_toilet_paper') or None
        if default_toilet_paper:
            unit.default_toilet_paper = int(default_toilet_paper)
        else:
            unit.default_toilet_paper = None

        default_towel = request.form.get('default_towel') or None
        if default_towel:
            unit.default_towel = int(default_towel)
        else:
            unit.default_towel = None

        default_garbage_bag = request.form.get('default_garbage_bag') or None
        if default_garbage_bag:
            unit.default_garbage_bag = int(default_garbage_bag)
        else:
            unit.default_garbage_bag = None

        monthly_rent = request.form.get('monthly_rent') or None
        if monthly_rent:
            unit.monthly_rent = float(monthly_rent)
        else:
            unit.monthly_rent = None

        max_pax = request.form.get('max_pax') or None
        if max_pax:
            unit.max_pax = int(max_pax)
        else:
            unit.max_pax = None

        db.session.commit()
        flash('Unit updated successfully', 'success')
        return redirect(url_for('units.manage_units'))

    return render_template('edit_unit_user.html', unit=unit)


@units_bp.route('/delete_unit/<int:id>', methods=['POST'])
@login_required
def delete_unit(id):
    unit = Unit.query.get_or_404(id)

    # Check if the unit belongs to the user's company
    if unit.company_id != current_user.company_id:
        flash('You do not have permission to delete this unit', 'danger')
        return redirect(url_for('units.manage_units'))

    # Check if user can access this unit
    if not check_unit_access(id):
        flash('You do not have permission to delete this unit', 'danger')
        return redirect(url_for('units.manage_units'))

    try:
        # First, delete all associated data manually to ensure everything is removed

        # Delete expense data for this unit
        ExpenseData.query.filter_by(unit_id=unit.id).delete()

        # Delete expense remarks for this unit
        ExpenseRemark.query.filter_by(unit_id=unit.id).delete()

        # Delete bookings for this unit
        BookingForm.query.filter_by(unit_id=unit.id).delete()

        # Delete calendar sources for this unit
        CalendarSource.query.filter_by(unit_id=unit.id).delete()

        # Delete issues for this unit
        Issue.query.filter_by(unit_id=unit.id).delete()

        # Delete complaints for this unit
        Complaint.query.filter_by(unit_id=unit.id).delete()

        # Delete repairs for this unit
        Repair.query.filter_by(unit_id=unit.id).delete()

        # Delete replacements for this unit
        Replacement.query.filter_by(unit_id=unit.id).delete()

        # Remove this unit from cleaner assignments (many-to-many)
        for cleaner in unit.assigned_cleaners:
            cleaner.assigned_units.remove(unit)

        # Finally, delete the unit itself
        db.session.delete(unit)
        db.session.commit()

        flash('Unit deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting unit: {str(e)}', 'danger')

    return redirect(url_for('units.manage_units'))


@units_bp.route('/confirm_delete_unit/<int:id>')
@login_required
def confirm_delete_unit(id):
    unit = Unit.query.get_or_404(id)

    # Check if the unit belongs to the user's company
    if unit.company_id != current_user.company_id:
        flash('You do not have permission to delete this unit', 'danger')
        return redirect(url_for('units.manage_units'))

    # Count related data
    expense_count = ExpenseData.query.filter_by(unit_id=unit.id).count()
    booking_count = BookingForm.query.filter_by(unit_id=unit.id).count()
    issue_count = Issue.query.filter_by(unit_id=unit.id).count()
    complaint_count = Complaint.query.filter_by(unit_id=unit.id).count()
    repair_count = Repair.query.filter_by(unit_id=unit.id).count()
    replacement_count = Replacement.query.filter_by(unit_id=unit.id).count()

    return render_template('confirm_delete_unit.html',
                           unit=unit,
                           expense_count=expense_count,
                           booking_count=booking_count,
                           issue_count=issue_count,
                           complaint_count=complaint_count,
                           repair_count=repair_count,
                           replacement_count=replacement_count)


@units_bp.route('/unit/<int:id>')
@login_required
def unit_info(id):
    # Get the unit by id
    unit = Unit.query.get_or_404(id)

    # Check if the unit belongs to the user's company
    if unit.company_id != current_user.company_id:
        flash('You do not have permission to view this unit', 'danger')
        return redirect(url_for('units.manage_units'))

    # Check if user can access this unit
    if not check_unit_access(id):
        flash('You do not have permission to view this unit', 'danger')
        return redirect(url_for('units.manage_units'))

    # Get issues for this unit
    issues = Issue.query.filter_by(unit_id=unit.id).order_by(Issue.date_added.desc()).limit(10).all()

    return render_template('unit_info.html', unit=unit, issues=issues)

# API route to get units for the current user's company
@units_bp.route('/api/get_units')
@login_required
def get_units():
    # Use access control to get only accessible units
    units = get_accessible_units_query().all()
    units_list = [{'id': unit.id, 'unit_number': unit.unit_number} for unit in units]
    return jsonify(units_list)