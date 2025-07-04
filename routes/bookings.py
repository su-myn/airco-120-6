from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from functools import wraps
from models import db, BookingForm, Unit
from utils.access_control import (
    filter_query_by_accessible_units,
    get_accessible_units_query,
    get_accessible_bookings_query,
    get_accessible_issues_query,
    check_unit_access,
    require_unit_access
)
import pytz

bookings_bp = Blueprint('bookings', __name__)



def convert_utc_to_malaysia_time(utc_dt):
    """Convert UTC datetime to Malaysia timezone"""
    if utc_dt is None:
        return None
    malaysia_tz = pytz.timezone('Asia/Kuala_Lumpur')
    if utc_dt.tzinfo is None:
        utc_dt = pytz.utc.localize(utc_dt)
    return utc_dt.astimezone(malaysia_tz)


# Permission decorator
def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.has_permission(permission):
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('dashboard.dashboard'))
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def check_unit_availability(unit_id, check_in_date, check_out_date, exclude_booking_id=None):
    """
    Check if a unit is available for the given date range
    Returns True if available, False if there's a conflict

    Updated logic to allow same-day turnover:
    - Guest A can check out on June 27
    - Guest B can check in on June 27 (same day)
    """

    # Find conflicting bookings with updated logic
    query = BookingForm.query.filter(
        BookingForm.unit_id == unit_id,
        # True overlap: new check-in is before existing check-out AND new check-out is after existing check-in
        BookingForm.check_in_date < check_out_date,
        BookingForm.check_out_date > check_in_date
    )

    # ALLOW same-day turnover by excluding these scenarios:
    # 1. New check-in date equals existing check-out date (someone checks out, we check in same day)
    # 2. New check-out date equals existing check-in date (we check out, someone checks in same day)
    query = query.filter(
        ~((BookingForm.check_out_date == check_in_date) |  # Allow check-in on checkout day
          (BookingForm.check_in_date == check_out_date))   # Allow check-out on checkin day
    )

    # Exclude the current booking if we're updating
    if exclude_booking_id:
        query = query.filter(BookingForm.id != exclude_booking_id)

    # If any booking exists in this range (after excluding same-day turnovers), the unit is not available
    return query.count() == 0


@bookings_bp.route('/bookings')
@login_required
@permission_required('can_view_bookings')
def bookings():
    # Filter bookings to only show those for accessible units
    bookings_list = get_accessible_bookings_query().order_by(
        BookingForm.date_added.desc()).all()

    # Get accessible units for this user for the form
    units = get_accessible_units_query().all()

    # Calculate analytics for the dashboard using accessible units only
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    # Get accessible unit IDs for filtering - ONLY ACTIVE UNITS
    accessible_active_units = get_accessible_units_query().filter(Unit.is_occupied == True).all()
    accessible_unit_ids = [unit.id for unit in accessible_active_units]

    if not accessible_unit_ids:
        # If no accessible active units, return zero stats
        stats = {
            'unit_total': 0,
            'occupancy_current': 0,
            'occupancy_tomorrow': 0,
            'check_ins_today': 0,
            'revenue_today': '0.00',
            'revenue_tomorrow': '0.00',
            'check_ins_tomorrow': 0,
            'check_outs_today': 0,
            'check_outs_tomorrow': 0
        }
        return render_template('bookings.html', bookings=bookings_list, units=units, stats=stats, active_filter=None)

    # Calculate total accessible ACTIVE units only
    unit_total = len(accessible_unit_ids)

    # Calculate occupancy today (units where check-in <= today < check-out)
    occupancy_current = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_in_date <= today,
        BookingForm.check_out_date > today
    ).count()

    # Calculate occupancy tomorrow (units where check-in <= tomorrow < check-out)
    occupancy_tomorrow = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_in_date <= tomorrow,
        BookingForm.check_out_date > tomorrow
    ).count()

    # Calculate check-ins today
    check_ins_today = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_in_date == today
    ).count()

    # Calculate revenue today (total price of bookings with check-in today)
    today_check_ins = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_in_date == today
    ).all()
    revenue_today = sum(float(booking.price) for booking in today_check_ins if booking.price)

    # Calculate revenue tomorrow (total price of bookings with check-in tomorrow)
    tomorrow_check_ins = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_in_date == tomorrow
    ).all()
    revenue_tomorrow = sum(float(booking.price) for booking in tomorrow_check_ins if booking.price)

    # Calculate check-ins tomorrow
    check_ins_tomorrow = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_in_date == tomorrow
    ).count()

    # Calculate check-outs today
    check_outs_today = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_out_date == today
    ).count()

    # Calculate check-outs tomorrow
    check_outs_tomorrow = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_out_date == tomorrow
    ).count()

    # Create stats dictionary
    stats = {
        'unit_total': unit_total,
        'occupancy_current': occupancy_current,
        'occupancy_tomorrow': occupancy_tomorrow,
        'check_ins_today': check_ins_today,
        'revenue_today': '{:,.2f}'.format(revenue_today),
        'revenue_tomorrow': '{:,.2f}'.format(revenue_tomorrow),
        'check_ins_tomorrow': check_ins_tomorrow,
        'check_outs_today': check_outs_today,
        'check_outs_tomorrow': check_outs_tomorrow
    }

    return render_template('bookings.html', bookings=bookings_list, units=units, stats=stats, active_filter=None)



# Replace the existing bookings_filter() function with this updated version:
@bookings_bp.route('/bookings/<filter_type>')
@login_required
@permission_required('can_view_bookings')
def bookings_filter(filter_type):
    # Get accessible units for this user
    units = get_accessible_units_query().all()

    # Get accessible ACTIVE units only for calculations
    accessible_active_units = get_accessible_units_query().filter(Unit.is_occupied == True).all()
    accessible_unit_ids = [unit.id for unit in accessible_active_units]

    # Calculate analytics for the dashboard
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    if not accessible_unit_ids:
        # If no accessible active units, return empty results
        stats = {
            'unit_total': 0,
            'occupancy_current': 0,
            'occupancy_tomorrow': 0,
            'check_ins_today': 0,
            'revenue_today': '0.00',
            'revenue_tomorrow': '0.00',
            'check_ins_tomorrow': 0,
            'check_outs_today': 0,
            'check_outs_tomorrow': 0
        }
        return render_template('bookings.html',
                               bookings=[],
                               units=units,
                               stats=stats,
                               filter_message="No accessible active units",
                               active_filter=filter_type)

    # Calculate all the stats using only active units
    unit_total = len(accessible_unit_ids)

    occupancy_current = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_in_date <= today,
        BookingForm.check_out_date > today
    ).count()

    occupancy_tomorrow = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_in_date <= tomorrow,
        BookingForm.check_out_date > tomorrow
    ).count()

    check_ins_today = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_in_date == today
    ).count()

    today_check_ins = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_in_date == today
    ).all()
    revenue_today = sum(float(booking.price) for booking in today_check_ins if booking.price)

    tomorrow_check_ins = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_in_date == tomorrow
    ).all()
    revenue_tomorrow = sum(float(booking.price) for booking in tomorrow_check_ins if booking.price)

    check_ins_tomorrow = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_in_date == tomorrow
    ).count()

    check_outs_today = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_out_date == today
    ).count()

    check_outs_tomorrow = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_out_date == tomorrow
    ).count()

    # Apply specific filter based on filter_type (all filtered by accessible active units)
    base_query = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids)
    )

    if filter_type == 'occupancy_current':
        bookings_list = base_query.filter(
            BookingForm.check_in_date <= today,
            BookingForm.check_out_date > today
        ).all()
        filter_message = "Showing currently occupied units"

    elif filter_type == 'occupancy_tomorrow':
        bookings_list = base_query.filter(
            BookingForm.check_in_date <= tomorrow,
            BookingForm.check_out_date > tomorrow
        ).all()
        filter_message = f"Showing units that will be occupied tomorrow ({tomorrow.strftime('%b %d, %Y')})"

    elif filter_type == 'check_ins_today':
        bookings_list = base_query.filter(
            BookingForm.check_in_date == today
        ).all()
        filter_message = f"Showing check-ins for today ({today.strftime('%b %d, %Y')})"

    elif filter_type == 'revenue_today':
        bookings_list = base_query.filter(
            BookingForm.check_in_date == today
        ).all()
        filter_message = f"Showing revenue for today ({today.strftime('%b %d, %Y')})"

    elif filter_type == 'revenue_tomorrow':
        bookings_list = base_query.filter(
            BookingForm.check_in_date == tomorrow
        ).all()
        filter_message = f"Showing revenue for tomorrow ({tomorrow.strftime('%b %d, %Y')})"

    elif filter_type == 'check_ins_tomorrow':
        bookings_list = base_query.filter(
            BookingForm.check_in_date == tomorrow
        ).all()
        filter_message = f"Showing check-ins for tomorrow ({tomorrow.strftime('%b %d, %Y')})"

    elif filter_type == 'check_outs_today':
        bookings_list = base_query.filter(
            BookingForm.check_out_date == today
        ).all()
        filter_message = f"Showing check-outs for today ({today.strftime('%b %d, %Y')})"

    elif filter_type == 'check_outs_tomorrow':
        bookings_list = base_query.filter(
            BookingForm.check_out_date == tomorrow
        ).all()
        filter_message = f"Showing check-outs for tomorrow ({tomorrow.strftime('%b %d, %Y')})"

    else:
        # Default - show all accessible bookings
        bookings_list = base_query.all()
        filter_message = None

    # Create stats dictionary
    stats = {
        'unit_total': unit_total,
        'occupancy_current': occupancy_current,
        'occupancy_tomorrow': occupancy_tomorrow,
        'check_ins_today': check_ins_today,
        'revenue_today': '{:,.2f}'.format(revenue_today),
        'revenue_tomorrow': '{:,.2f}'.format(revenue_tomorrow),
        'check_ins_tomorrow': check_ins_tomorrow,
        'check_outs_today': check_outs_today,
        'check_outs_tomorrow': check_outs_tomorrow
    }

    return render_template('bookings.html',
                           bookings=bookings_list,
                           units=units,
                           stats=stats,
                           filter_message=filter_message,
                           active_filter=filter_type)


# Replace the existing add_booking() function with this updated version:
@bookings_bp.route('/add_booking', methods=['GET', 'POST'])
@login_required
@permission_required('can_manage_bookings')
def add_booking():
    if request.method == 'POST':
        # ... existing form processing code until unit_id validation ...
        unit_id = request.form['unit_id']

        # DEBUG: Let's see what's happening
        print(f"DEBUG: User {current_user.email} trying to book unit_id: {unit_id}")
        print(f"DEBUG: User role: {current_user.role.name}")
        print(f"DEBUG: User accessible unit IDs: {current_user.get_accessible_unit_ids()}")
        print(f"DEBUG: Unit {unit_id} in accessible units? {int(unit_id) in current_user.get_accessible_unit_ids()}")
        print(f"DEBUG: check_unit_access result: {check_unit_access(unit_id)}")


        # Check if user can access this unit
        if not check_unit_access(unit_id):
            flash('You do not have permission to book this unit', 'danger')
            units = get_accessible_units_query().all()
            return render_template('booking_form.html', units=units)

        # ... rest of the existing add_booking code remains the same ...
        guest_name = request.form['guest_name']
        contact_number = request.form['contact_number']
        check_in_date = datetime.strptime(request.form['check_in_date'], '%Y-%m-%d').date()
        check_out_date = datetime.strptime(request.form['check_out_date'], '%Y-%m-%d').date()
        property_name = request.form['property_name']
        number_of_nights = (check_out_date - check_in_date).days

        # Calculate number_of_guests from the sum
        adults = int(request.form.get('adults', 0) or 0)
        children = int(request.form.get('children', 0) or 0)
        infants = int(request.form.get('infants', 0) or 0)
        number_of_guests = adults + children + infants

        price = request.form['price']
        booking_source = request.form['booking_source']
        payment_status = request.form['payment_status']
        notes = request.form['notes']

        # Handle new fields
        confirmation_code = request.form.get('confirmation_code', '')

        # Process booking date (if provided)
        booking_date = None
        if request.form.get('booking_date'):
            booking_date = datetime.strptime(request.form['booking_date'], '%Y-%m-%d').date()

        # Check for date conflicts with existing bookings
        is_available = check_unit_availability(
            unit_id,
            check_in_date,
            check_out_date
        )

        if not is_available:
            flash(f'Unit is not available for these dates. There is already a booking that overlaps with this period.',
                  'danger')
            # Get accessible units for the form again
            units = get_accessible_units_query().all()
            return render_template('booking_form.html', units=units)

        # Get the unit and verify access again
        unit = Unit.query.get(unit_id)
        if not unit or not check_unit_access(unit_id):
            flash('Invalid unit selected or access denied', 'danger')
            return redirect(url_for('bookings.add_booking'))

        new_booking = BookingForm(
            guest_name=guest_name,
            contact_number=contact_number,
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            property_name=property_name,
            unit_id=unit_id,
            number_of_nights=number_of_nights,
            number_of_guests=number_of_guests,
            price=price,
            booking_source=booking_source,
            payment_status=payment_status,
            notes=notes,
            # New fields
            confirmation_code=confirmation_code,
            booking_date=booking_date,
            adults=adults,
            children=children,
            infants=infants,
            # Existing fields
            company_id=current_user.company_id,
            user_id=current_user.id
        )

        db.session.add(new_booking)
        db.session.commit()

        # FIXED: Use a list instead of a single ID
        if 'highlight_booking_ids' not in session:
            session['highlight_booking_ids'] = []
        session['highlight_booking_ids'].append(new_booking.id)

        flash('Booking added successfully', 'success')
        return redirect(url_for('bookings.bookings', highlight_id=new_booking.id))

    # Get accessible units for the form
    units = get_accessible_units_query().all()

    return render_template('booking_form.html', units=units)


# Replace the existing update_booking() function with this updated version:
@bookings_bp.route('/update_booking/<int:id>', methods=['POST'])
@login_required
@permission_required('can_manage_bookings')
def update_booking(id):
    booking = BookingForm.query.get_or_404(id)

    # Ensure the current user's company matches the booking's company
    if booking.company_id != current_user.company_id:
        flash('You are not authorized to update this booking', 'danger')
        return redirect(url_for('bookings.bookings'))

    # Check if user can access the current unit
    if not check_unit_access(booking.unit_id):
        flash('You do not have permission to access this booking', 'danger')
        return redirect(url_for('bookings.bookings'))

    # Check if user can access the new unit
    new_unit_id = request.form['unit_id']
    if not check_unit_access(new_unit_id):
        flash('You do not have permission to assign this booking to the selected unit', 'danger')
        return redirect(url_for('bookings.bookings'))

    # ... rest of the existing update_booking code remains the same ...
    # Update fields
    booking.guest_name = request.form.get('guest_name', '')
    booking.contact_number = request.form.get('contact_number', '')

    check_in_date = datetime.strptime(request.form['check_in_date'], '%Y-%m-%d').date()
    check_out_date = datetime.strptime(request.form['check_out_date'], '%Y-%m-%d').date()

    # Add validation to ensure check_out_date is after check_in_date
    if check_out_date <= check_in_date:
        flash('Check-out date must be after check-in date', 'danger')
        return redirect(url_for('bookings.bookings'))

    booking.check_in_date = check_in_date
    booking.check_out_date = check_out_date
    booking.number_of_nights = (check_out_date - check_in_date).days

    booking.property_name = request.form.get('property_name', '')
    booking.unit_id = request.form['unit_id']
    adults = int(request.form.get('adults', 0) or 0)
    children = int(request.form.get('children', 0) or 0)
    infants = int(request.form.get('infants', 0) or 0)
    number_of_guests = adults + children + infants
    booking.number_of_guests = number_of_guests
    booking.price = request.form['price']
    booking.booking_source = request.form['booking_source']
    booking.payment_status = request.form.get('payment_status', 'Pending')
    booking.notes = request.form.get('notes', '')

    # Update new fields
    booking.confirmation_code = request.form.get('confirmation_code', '')

    # Process booking date (if provided)
    if request.form.get('booking_date'):
        booking.booking_date = datetime.strptime(request.form['booking_date'], '%Y-%m-%d').date()

    # Check for date conflicts with existing bookings (excluding this booking)
    is_available = check_unit_availability(
        booking.unit_id,
        check_in_date,
        check_out_date,
        exclude_booking_id=id
    )

    if not is_available:
        flash(f'Unit is not available for these dates. There is already a booking that overlaps with this period.',
              'danger')
        return redirect(url_for('bookings.bookings'))

    # Process numeric fields
    adults = request.form.get('adults', '')
    booking.adults = int(adults) if adults.strip() else None

    children = request.form.get('children', '')
    booking.children = int(children) if children.strip() else None

    infants = request.form.get('infants', '')
    booking.infants = int(infants) if infants.strip() else None

    db.session.commit()

    # FIXED: Use a list instead of a single ID
    if 'highlight_booking_ids' not in session:
        session['highlight_booking_ids'] = []
    session['highlight_booking_ids'].append(id)

    flash('Booking updated successfully', 'success')
    return redirect(url_for('bookings.bookings', highlight_id=id))


# Replace the existing get_booking() function with this updated version:
@bookings_bp.route('/api/booking/<int:id>')
@login_required
@permission_required('can_view_bookings')
def get_booking(id):
    booking = BookingForm.query.get_or_404(id)

    # Ensure the current user's company matches the booking's company
    if booking.company_id != current_user.company_id:
        return jsonify({'error': 'Not authorized'}), 403

    # Check if user can access this unit
    if not check_unit_access(booking.unit_id):
        return jsonify({'error': 'Access denied to this unit'}), 403

    # Convert dates to Malaysia time
    malaysia_date_added = convert_utc_to_malaysia_time(booking.date_added)

    return jsonify({
        'id': booking.id,
        'guest_name': booking.guest_name,
        'contact_number': booking.contact_number,
        'check_in_date': booking.check_in_date.strftime('%Y-%m-%d'),
        'check_out_date': booking.check_out_date.strftime('%Y-%m-%d'),
        'date_added': malaysia_date_added.isoformat() if malaysia_date_added else None,
        'property_name': booking.property_name,
        'unit_id': booking.unit_id,
        'number_of_nights': booking.number_of_nights,
        'number_of_guests': booking.number_of_guests,
        'price': float(booking.price) if booking.price else 0,
        'booking_source': booking.booking_source,
        'payment_status': booking.payment_status,
        'notes': booking.notes,
        # Add new fields
        'confirmation_code': booking.confirmation_code,
        'booking_date': booking.booking_date.strftime('%Y-%m-%d') if booking.booking_date else '',
        'adults': booking.adults if booking.adults is not None else '',
        'children': booking.children if booking.children is not None else '',
        'infants': booking.infants if booking.infants is not None else ''
    })


# Replace the existing delete_booking() function with this updated version:
@bookings_bp.route('/delete_booking/<int:id>')
@login_required
@permission_required('can_manage_bookings')
def delete_booking(id):
    booking = BookingForm.query.get_or_404(id)

    # Ensure the current user's company matches the booking's company
    if booking.company_id != current_user.company_id:
        flash('You are not authorized to delete this booking', 'danger')
        return redirect(url_for('bookings.bookings'))

    # Check if user can access this unit
    if not check_unit_access(booking.unit_id):
        flash('You do not have permission to access this booking', 'danger')
        return redirect(url_for('bookings.bookings'))

    db.session.delete(booking)
    db.session.commit()

    flash('Booking deleted successfully', 'success')
    return redirect(url_for('bookings.bookings'))


# Replace the existing get_unit_bookings() function with this updated version:
@bookings_bp.route('/api/unit_bookings/<int:unit_id>')
@login_required
def get_unit_bookings(unit_id):
    """
    Get all bookings for a specific unit to determine unavailable dates
    """
    # Check if the user can access this unit
    if not check_unit_access(unit_id):
        return jsonify({'error': 'You do not have permission to access this unit'}), 403

    # Get all bookings for this unit
    bookings = BookingForm.query.filter_by(unit_id=unit_id).all()

    # Format the booking data
    booking_data = []
    for booking in bookings:
        booking_data.append({
            'id': booking.id,
            'check_in_date': booking.check_in_date.isoformat(),
            'check_out_date': booking.check_out_date.isoformat(),
            'guest_name': booking.guest_name
        })

    unit = Unit.query.get(unit_id)
    return jsonify({
        'unit_id': unit_id,
        'unit_number': unit.unit_number if unit else 'Unknown',
        'bookings': booking_data
    })


# Replace the existing check_availability() function with this updated version:
@bookings_bp.route('/api/check_availability')
@login_required
def check_availability():
    unit_id = request.args.get('unit_id', type=int)
    check_in = request.args.get('check_in')
    check_out = request.args.get('check_out')
    booking_id = request.args.get('booking_id', type=int)  # Optional, for updates

    if not unit_id or not check_in or not check_out:
        return jsonify({'available': False, 'error': 'Missing parameters'})

    # Check if user can access this unit
    if not check_unit_access(unit_id):
        return jsonify({'available': False, 'error': 'Access denied to this unit'})

    try:
        # Convert string dates to datetime objects
        check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
        check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()

        # Validate dates (check-out must be after check-in)
        if check_out_date <= check_in_date:
            return jsonify({
                'available': False,
                'error': 'Check-out date must be after check-in date'
            })

        # Check availability
        is_available = check_unit_availability(unit_id, check_in_date, check_out_date, booking_id)

        # If not available, find the conflicting bookings
        conflicting_bookings = []
        if not is_available:
            conflicts = BookingForm.query.filter(
                BookingForm.unit_id == unit_id,
                BookingForm.check_in_date < check_out_date,
                BookingForm.check_out_date > check_in_date
            )

            # Exclude the current booking if we're updating
            if booking_id:
                conflicts = conflicts.filter(BookingForm.id != booking_id)

            # Format the conflicts
            for booking in conflicts:
                conflicting_bookings.append({
                    'id': booking.id,
                    'check_in_date': booking.check_in_date.isoformat(),
                    'check_out_date': booking.check_out_date.isoformat(),
                    'guest_name': booking.guest_name
                })

        return jsonify({
            'available': is_available,
            'unit_id': unit_id,
            'check_in_date': check_in,
            'check_out_date': check_out,
            'conflicts': conflicting_bookings
        })
    except Exception as e:
        return jsonify({'available': False, 'error': str(e)})


# FIXED: Return the session variable as a list
@bookings_bp.route('/api/get_highlighted_bookings')
@login_required
def get_highlighted_bookings():
    """API endpoint to get IDs of bookings that should be highlighted"""
    # Get highlight IDs from session - ensure it's always a list
    highlight_ids = session.get('highlight_booking_ids', [])

    # Ensure highlight_ids is a list (handle legacy single ID case)
    if not isinstance(highlight_ids, list):
        highlight_ids = [highlight_ids] if highlight_ids else []

    # Clear the session variable after retrieving it
    if 'highlight_booking_ids' in session:
        session.pop('highlight_booking_ids')

    return jsonify({'highlight_ids': highlight_ids})


@bookings_bp.route('/api/import_airbnb_csv', methods=['POST'])
@login_required
@permission_required('can_manage_bookings')
def import_airbnb_csv():
    # Get the bookings data from the request
    if not request.is_json:
        return jsonify({'success': False, 'message': 'Invalid request format. JSON expected.'}), 400

    data = request.json
    bookings = data.get('bookings', [])

    if not bookings:
        return jsonify({'success': False, 'message': 'No booking data provided.'}), 400

    # Get the user's company ID
    company_id = current_user.company_id

    # Counters for tracking what happened
    created_count = 0
    updated_count = 0
    error_count = 0

    # FIXED: Collect only booking IDs that actually had changes
    updated_booking_ids = []

    for booking_data in bookings:
        try:
            # Check if confirmation code exists
            confirmation_code = booking_data.get('confirmation_code')
            if not confirmation_code:
                error_count += 1
                continue

            # Check if we already have this booking in our database
            existing_booking = BookingForm.query.filter_by(
                confirmation_code=confirmation_code,
                company_id=company_id
            ).first()

            # If booking exists, check if it needs updating
            if existing_booking:
                # Track if any changes were actually made
                has_changes = False

                # Convert date strings to date objects
                try:
                    check_in_date = datetime.strptime(booking_data.get('check_in_date', ''), '%Y-%m-%d').date()
                    check_out_date = datetime.strptime(booking_data.get('check_out_date', ''), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    # Try different date format (like MM/DD/YYYY)
                    try:
                        check_in_date = datetime.strptime(booking_data.get('check_in_date', ''), '%m/%d/%Y').date()
                        check_out_date = datetime.strptime(booking_data.get('check_out_date', ''), '%m/%d/%Y').date()
                    except (ValueError, TypeError):
                        # Keep existing dates if parsing fails
                        check_in_date = existing_booking.check_in_date
                        check_out_date = existing_booking.check_out_date

                # Try to parse booking date
                booking_date = None
                if booking_data.get('booking_date'):
                    parsed_date = parse_date(booking_data.get('booking_date'))
                    if parsed_date and parsed_date != existing_booking.booking_date:
                        existing_booking.booking_date = parsed_date
                        has_changes = True

                # Check and update guest name if it changed
                new_guest_name = booking_data.get('guest_name')
                if new_guest_name and new_guest_name != existing_booking.guest_name:
                    existing_booking.guest_name = new_guest_name
                    has_changes = True

                # Check and update contact number if it changed
                new_contact_number = booking_data.get('contact_number')
                if new_contact_number and new_contact_number != existing_booking.contact_number:
                    existing_booking.contact_number = new_contact_number
                    has_changes = True

                # Check and update dates if they changed
                if (check_in_date and check_out_date and check_in_date < check_out_date and
                    (check_in_date != existing_booking.check_in_date or
                     check_out_date != existing_booking.check_out_date)):
                    existing_booking.check_in_date = check_in_date
                    existing_booking.check_out_date = check_out_date
                    # Calculate nights from the dates
                    new_nights = (check_out_date - check_in_date).days
                    if new_nights != existing_booking.number_of_nights:
                        existing_booking.number_of_nights = new_nights
                        has_changes = True
                    else:
                        has_changes = True  # Dates changed even if nights stayed same

                # Check and update price if it changed
                if booking_data.get('price'):
                    try:
                        # Handle price as string, removing any non-numeric characters except periods
                        price_str = str(booking_data.get('price'))
                        # Remove any remaining 'RM' if it wasn't caught by JavaScript
                        price_str = price_str.replace('RM', '').replace(',', '').strip()
                        price_value = float(price_str)

                        if price_value > 0 and abs(float(existing_booking.price or 0) - price_value) > 0.01:
                            existing_booking.price = price_value
                            has_changes = True
                    except (ValueError, TypeError) as e:
                        print(f"Failed to convert price: {booking_data.get('price')} - Error: {e}")

                # Check and update payment status if it changed
                new_payment_status = booking_data.get('payment_status')
                if new_payment_status and new_payment_status != existing_booking.payment_status:
                    existing_booking.payment_status = new_payment_status
                    has_changes = True

                # Check and update guest counts if they changed
                new_adults = booking_data.get('adults', 0)
                new_children = booking_data.get('children', 0)
                new_infants = booking_data.get('infants', 0)

                if (new_adults > 0 and new_adults != (existing_booking.adults or 0)):
                    existing_booking.adults = new_adults
                    has_changes = True

                if (new_children > 0 and new_children != (existing_booking.children or 0)):
                    existing_booking.children = new_children
                    has_changes = True

                if (new_infants > 0 and new_infants != (existing_booking.infants or 0)):
                    existing_booking.infants = new_infants
                    has_changes = True

                # Update total number of guests if guest counts changed
                new_total_guests = (
                    (existing_booking.adults or 0) +
                    (existing_booking.children or 0) +
                    (existing_booking.infants or 0)
                )
                if new_total_guests != existing_booking.number_of_guests:
                    existing_booking.number_of_guests = new_total_guests
                    has_changes = True

                # FIXED: Only add to highlight list if there were actual changes
                if has_changes:
                    updated_booking_ids.append(existing_booking.id)
                    updated_count += 1
            else:
                # This is a new booking - we would normally create it, but
                # in this case we'll skip it since we want to focus on updating existing bookings
                pass

        except Exception as e:
            error_count += 1
            print(f"Error processing booking: {e}")

    # Commit all changes
    db.session.commit()

    # FIXED: Store only booking IDs that actually had changes in session for highlighting
    if updated_booking_ids:
        session['highlight_booking_ids'] = updated_booking_ids

    # Return the result
    return jsonify({
        'success': True,
        'message': f"Successfully processed bookings. Updated: {updated_count}, No changes: {len(bookings) - updated_count - error_count}, Errors: {error_count}",
        'updated': updated_count,
        'created': created_count,
        'errors': error_count
    })


def parse_date(date_str):
    """Helper function to parse dates in various formats"""
    if not date_str or not date_str.strip():
        return None

    date_str = date_str.strip()

    # Try standard formats
    formats = [
        '%b %d, %Y',  # Jan 03, 2025
        '%B %d, %Y',  # January 03, 2025
        '%Y-%m-%d',  # 2025-01-03
        '%d/%m/%Y',  # 03/01/2025
        '%m/%d/%Y'  # 01/03/2025
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    # Try to handle formats with single-digit days (without leading zeros)
    # This is trickier in Python as strptime expects exact format matches

    # Parse month names manually
    month_names = {
        'jan': 1, 'january': 1,
        'feb': 2, 'february': 2,
        'mar': 3, 'march': 3,
        'apr': 4, 'april': 4,
        'may': 5, 'may': 5,
        'jun': 6, 'june': 6,
        'jul': 7, 'july': 7,
        'aug': 8, 'august': 8,
        'sep': 9, 'september': 9,
        'oct': 10, 'october': 10,
        'nov': 11, 'november': 11,
        'dec': 12, 'december': 12
    }

    # Check if it matches pattern like "Jan 3, 2025"
    import re
    match = re.match(r'([a-zA-Z]+)\s+(\d{1,2}),\s+(\d{4})', date_str)
    if match:
        month_name, day, year = match.groups()
        month_num = month_names.get(month_name.lower())
        if month_num:
            try:
                return datetime(int(year), month_num, int(day)).date()
            except ValueError:
                pass

    # If all attempts fail, return None
    print(f"Could not parse date: {date_str}")
    return None