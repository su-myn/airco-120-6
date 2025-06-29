from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, User, Unit, Issue, Role, BookingForm
from datetime import datetime, timedelta
from utils.access_control import (
    get_accessible_units_query,
    get_accessible_bookings_query,
    check_unit_access
)

cleaners_bp = Blueprint('cleaners', __name__)

@cleaners_bp.route('/cleaner_dashboard')
@login_required
def cleaner_dashboard():
    # Check if the user is a cleaner
    if not current_user.is_cleaner:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    # Get assigned units (cleaners use the cleaner assignment system)
    assigned_units = current_user.assigned_units

    # Get issues related to those units (filter by accessible units for cleaners)
    issues = []
    if assigned_units:
        unit_ids = [unit.id for unit in assigned_units]
        issues = Issue.query.filter(
            Issue.unit_id.in_(unit_ids),
            Issue.company_id == current_user.company_id
        ).order_by(Issue.date_added.desc()).all()

    return render_template('cleaner_dashboard.html', units=assigned_units, issues=issues)

@cleaners_bp.route('/manage_cleaners')
@login_required
def manage_cleaners():
    # Check if user has permission to view manage cleaners
    if not current_user.has_permission('can_view_manage_cleaners'):
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    # Get all cleaners from the current user's company
    company_id = current_user.company_id
    cleaners = User.query.filter_by(company_id=company_id, is_cleaner=True).all()

    return render_template('manage_cleaners.html', cleaners=cleaners)


@cleaners_bp.route('/update_cleaner/<int:id>', methods=['GET', 'POST'])
@login_required
def update_cleaner(id):
    # Check if user has permission to manage cleaners
    if not current_user.has_permission('can_manage_manage_cleaners'):
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('cleaners.manage_cleaners'))

    # Get the cleaner
    cleaner = User.query.get_or_404(id)

    # Make sure the cleaner belongs to the same company as the manager
    if cleaner.company_id != current_user.company_id:
        flash('You do not have permission to update this cleaner.', 'danger')
        return redirect(url_for('cleaners.manage_cleaners'))

    # Get accessible units for this manager (not all company units)
    accessible_units = get_accessible_units_query().all()

    if request.method == 'POST':
        # Update cleaner information
        cleaner.phone_number = request.form.get('phone_number', '')

        # Update assigned units
        # First, clear current assignments
        cleaner.assigned_units = []

        # Then add new assignments (only from accessible units)
        selected_units = request.form.getlist('assigned_units')
        accessible_unit_ids = [str(unit.id) for unit in accessible_units]

        for unit_id in selected_units:
            # Only allow assignment to units the manager can access
            if unit_id in accessible_unit_ids:
                unit = Unit.query.get(unit_id)
                if unit and unit.company_id == current_user.company_id:
                    cleaner.assigned_units.append(unit)

        db.session.commit()
        flash('Cleaner information updated successfully', 'success')
        return redirect(url_for('cleaners.manage_cleaners'))

    return render_template('update_cleaner.html', cleaner=cleaner, units=accessible_units)


@cleaners_bp.route('/cleaning-schedule')
@login_required
def cleaning_schedule():
    # Allow cleaners to access their cleaning schedule, others need permission
    if not (current_user.is_cleaner or current_user.has_permission('can_view_jadual_pembersihan')):
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    tomorrow = datetime.now().date() + timedelta(days=1)

    # Get accessible units based on user role and access control
    if current_user.role.name in ['Manager', 'Admin'] or current_user.is_admin:
        # Managers and Admins see units based on access control
        accessible_units = get_accessible_units_query().all()
    elif current_user.role.name == 'Staff':
        # Staff users see units based on access control (not cleaner assignments)
        accessible_units = get_accessible_units_query().all()
    elif current_user.is_cleaner:
        # Cleaners see only their specifically assigned units
        accessible_units = current_user.assigned_units
    else:
        # Default: no access
        accessible_units = []

    accessible_unit_ids = [unit.id for unit in accessible_units]

    if not accessible_unit_ids:
        # No accessible units
        if current_user.role.name in ['Manager', 'Admin'] or current_user.is_admin:
            return render_template('cleaning_schedule_manager.html',
                                   cleaner_schedules=[],
                                   tomorrow=tomorrow)
        else:
            return render_template('cleaning_schedule.html',
                                   checkouts=[],
                                   tomorrow=tomorrow)

    # Get tomorrow's checkouts and check-ins (filtered by accessible units)
    checkouts_tomorrow = BookingForm.query.filter(
        BookingForm.check_out_date == tomorrow,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.company_id == current_user.company_id
    ).all()

    checkins_tomorrow = BookingForm.query.filter(
        BookingForm.check_in_date == tomorrow,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.company_id == current_user.company_id
    ).all()

    # Map unit_id to checkin booking for fast lookups
    checkin_map = {booking.unit_id: booking for booking in checkins_tomorrow}

    # For managers and admins, show all cleaners' schedules (but only for accessible units)
    if current_user.role.name in ['Manager', 'Admin', "Staff"] or current_user.is_admin:
        cleaners = User.query.filter_by(company_id=current_user.company_id, is_cleaner=True).all()

        cleaner_schedules = []
        for cleaner in cleaners:
            # Get units assigned to this cleaner that are also accessible to the manager/admin
            assigned_units = cleaner.assigned_units
            accessible_assigned_units = [unit for unit in assigned_units if unit.id in accessible_unit_ids]

            cleaner_checkouts = []

            for unit in accessible_assigned_units:
                for checkout in checkouts_tomorrow:
                    if checkout.unit_id == unit.id:
                        # Check if there's a check-in tomorrow for this unit
                        has_checkin = unit.id in checkin_map
                        checkin_booking = checkin_map.get(unit.id)

                        # Calculate supplies based on whether there's a check-in tomorrow
                        if has_checkin:
                            towels = checkin_booking.number_of_guests
                            rubbish_bags = checkin_booking.number_of_nights
                            toilet_rolls = checkin_booking.number_of_nights * (unit.toilet_count or 1)
                        else:
                            towels = unit.towel_count or 2
                            rubbish_bags = 2
                            toilet_rolls = 2 * (unit.toilet_count or 1)

                        cleaner_checkouts.append({
                            'unit': unit,
                            'checkout': checkout,
                            'has_checkin': has_checkin,
                            'checkin_booking': checkin_booking,
                            'towels': towels,
                            'rubbish_bags': rubbish_bags,
                            'toilet_rolls': toilet_rolls
                        })

            if cleaner_checkouts:
                cleaner_schedules.append({
                    'cleaner': cleaner,
                    'checkouts': cleaner_checkouts
                })

        return render_template('cleaning_schedule_manager.html',
                               cleaner_schedules=cleaner_schedules,
                               tomorrow=tomorrow)

    # For cleaners only, show individual schedule view
    else:
        # This now only applies to cleaners
        my_checkouts = []

        for unit in accessible_units:
            for checkout in checkouts_tomorrow:
                if checkout.unit_id == unit.id:
                    # Check if there's a check-in tomorrow for this unit
                    has_checkin = unit.id in checkin_map
                    checkin_booking = checkin_map.get(unit.id)

                    # Calculate supplies based on whether there's a check-in tomorrow
                    if has_checkin:
                        towels = checkin_booking.number_of_guests
                        rubbish_bags = checkin_booking.number_of_nights
                        toilet_rolls = checkin_booking.number_of_nights * (unit.toilet_count or 1)
                    else:
                        towels = unit.towel_count or 2
                        rubbish_bags = 2
                        toilet_rolls = 2 * (unit.toilet_count or 1)

                    my_checkouts.append({
                        'unit': unit,
                        'checkout': checkout,
                        'has_checkin': has_checkin,
                        'checkin_booking': checkin_booking,
                        'towels': towels,
                        'rubbish_bags': rubbish_bags,
                        'toilet_rolls': toilet_rolls
                    })

        return render_template('cleaning_schedule.html',
                               checkouts=my_checkouts,
                               tomorrow=tomorrow)