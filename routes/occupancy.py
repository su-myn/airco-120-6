from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Unit, BookingForm, Holiday, HolidayType
from datetime import datetime, timedelta, date
import calendar
from functools import wraps
import json
from utils.access_control import (
    get_accessible_units_query,
    get_accessible_bookings_query
)

occupancy_bp = Blueprint('occupancy', __name__)


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


@occupancy_bp.route('/occupancy')
@login_required
@permission_required('can_view_bookings')
def occupancy():
    # Get current month and year
    today = datetime.now()
    month = request.args.get('month', today.month, type=int)
    year = request.args.get('year', today.year, type=int)

    # Create calendar data
    cal = calendar.monthcalendar(year, month)
    month_name = calendar.month_name[month]

    # Get total accessible units for this user
    accessible_units = get_accessible_units_query().all()
    total_units = len(accessible_units)

    # Get all months for dropdown
    months = [(i, calendar.month_name[i]) for i in range(1, 13)]

    # Calculate previous and next month/year
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1

    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return render_template('occupancy.html',
                           cal=cal,
                           month=month,
                           year=year,
                           month_name=month_name,
                           months=months,
                           total_units=total_units,
                           prev_month=prev_month,
                           prev_year=prev_year,
                           next_month=next_month,
                           next_year=next_year,
                           today=today)


@occupancy_bp.route('/api/occupancy/<int:year>/<int:month>')
@login_required
def get_occupancy_data(year, month):
    # Get accessible unit IDs
    accessible_unit_ids = current_user.get_accessible_unit_ids()

    if not accessible_unit_ids:
        # If no accessible units, return empty data
        return jsonify({
            "occupancy": {},
            "total_units": 0,
            "holidays": {}
        })

    # Get the first and last day of the month
    first_day = date(year, month, 1)
    # Get the last day of the month
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    # Get bookings that overlap with this month for accessible units only
    bookings = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        BookingForm.check_in_date <= last_day,
        BookingForm.check_out_date >= first_day
    ).all()

    # Calculate occupancy for each day of the month
    calendar_days = calendar.monthcalendar(year, month)
    days_in_month = len([day for week in calendar_days for day in week if day != 0])

    # Initialize occupancy data
    occupancy_data = {day: 0 for day in range(1, days_in_month + 1)}

    # Count occupied units for each day
    for booking in bookings:
        start_date = max(booking.check_in_date, first_day)
        end_date = min(booking.check_out_date, last_day)

        current_date = start_date
        while current_date < end_date:  # Don't count checkout day
            if current_date.month == month and current_date.year == year:
                occupancy_data[current_date.day] += 1
            current_date += timedelta(days=1)

    # Get total accessible units
    total_units = len(accessible_unit_ids)

    # Get holidays for this month (existing holiday logic remains the same)
    holiday_data = {}

    # First get public and school holidays from the system
    holiday_types = HolidayType.query.filter(
        HolidayType.name.in_(["Malaysia Public Holiday", "Malaysia School Holiday", "Custom Holiday"])
    ).all()

    for holiday_type in holiday_types:
        # Get deleted holiday dates for this company
        deleted_holidays = Holiday.query.filter(
            Holiday.holiday_type_id == holiday_type.id,
            Holiday.company_id == current_user.company_id,
            Holiday.is_deleted == True,
            Holiday.date.between(first_day, last_day)
        ).all()
        deleted_dates = {h.date for h in deleted_holidays}

        # Get company-specific additions
        company_holidays = Holiday.query.filter(
            Holiday.holiday_type_id == holiday_type.id,
            Holiday.company_id == current_user.company_id,
            Holiday.is_deleted == False,
            Holiday.date.between(first_day, last_day)
        ).all()

        # Add company-specific holidays
        for holiday in company_holidays:
            day = holiday.date.day
            if day not in holiday_data:
                holiday_data[day] = []

            # Determine holiday type for display
            if "Public" in holiday_type.name:
                type_class = "public"
            elif "School" in holiday_type.name:
                type_class = "school"
            else:
                type_class = "custom"

            holiday_data[day].append({
                "name": holiday.name,
                "type": type_class,
                "color": holiday_type.color
            })

        # If it's a system holiday type, add system holidays that aren't deleted by this company
        if holiday_type.name != "Custom Holiday":
            system_holidays = Holiday.query.filter(
                Holiday.holiday_type_id == holiday_type.id,
                Holiday.company_id == None,
                Holiday.date.between(first_day, last_day)
            ).all()

            for holiday in system_holidays:
                # Skip if this date is marked as deleted for this company
                if holiday.date in deleted_dates:
                    continue

                day = holiday.date.day
                if day not in holiday_data:
                    holiday_data[day] = []

                # Determine holiday type for display
                if "Public" in holiday_type.name:
                    type_class = "public"
                elif "School" in holiday_type.name:
                    type_class = "school"
                else:
                    type_class = "custom"

                holiday_data[day].append({
                    "name": holiday.name,
                    "type": type_class,
                    "color": holiday_type.color
                })

    return jsonify({
        "occupancy": occupancy_data,
        "total_units": total_units,
        "holidays": holiday_data
    })


@occupancy_bp.route('/add_custom_holiday', methods=['GET', 'POST'])
@login_required
def add_custom_holiday():
    if request.method == 'POST':
        name = request.form.get('name')
        holiday_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        is_recurring = 'is_recurring' in request.form

        # Get the Custom Holiday type (or create it if it doesn't exist)
        custom_type = HolidayType.query.filter_by(name="Custom Holiday").first()
        if not custom_type:
            custom_type = HolidayType(name="Custom Holiday", color="#9C27B0", is_system=True)
            db.session.add(custom_type)
            db.session.commit()

        # Create the holiday
        holiday = Holiday(
            name=name,
            date=holiday_date,
            holiday_type_id=custom_type.id,
            company_id=current_user.company_id,
            is_recurring=is_recurring
        )

        db.session.add(holiday)
        db.session.commit()

        flash(f'Custom holiday "{name}" added successfully!', 'success')
        return redirect(url_for('occupancy.occupancy'))

    return render_template('add_custom_holiday.html')


@occupancy_bp.route('/manage_holidays')
@login_required
def manage_holidays():
    # Default to public holidays if no type specified
    holiday_type = request.args.get('type', 'public')

    # Get the success message from query params if any
    success_message = request.args.get('success_message')

    # Validate holiday type
    if holiday_type not in ['public', 'school', 'custom']:
        holiday_type = 'public'

    # Get appropriate holiday type ID
    if holiday_type == 'public':
        type_name = "Malaysia Public Holiday"
    elif holiday_type == 'school':
        type_name = "Malaysia School Holiday"
    else:
        type_name = "Custom Holiday"

    # Get the holiday type object
    holiday_type_obj = HolidayType.query.filter_by(name=type_name).first()

    if not holiday_type_obj:
        # Create the holiday type if it doesn't exist
        if holiday_type == 'public':
            color = "#4CAF50"  # Green
        elif holiday_type == 'school':
            color = "#2196F3"  # Blue
        else:
            color = "#9C27B0"  # Purple

        holiday_type_obj = HolidayType(name=type_name, color=color, is_system=True)
        db.session.add(holiday_type_obj)
        db.session.commit()

    # This is key: We need to get BOTH system holidays AND company-specific overrides
    holidays = []

    if holiday_type == 'custom':
        # Custom days are always company-specific
        holidays = Holiday.query.filter_by(
            holiday_type_id=holiday_type_obj.id,
            company_id=current_user.company_id,
            is_deleted=False  # Filter out deleted holidays
        ).order_by(Holiday.date).all()
    else:
        # For public and school holidays, merge both lists
        company_holidays = Holiday.query.filter_by(
            holiday_type_id=holiday_type_obj.id,
            company_id=current_user.company_id,
            is_deleted=False  # Filter out deleted holidays
        ).order_by(Holiday.date).all()

        # Add the company-specific holidays first
        holidays.extend(company_holidays)

        # Create a set of dates for quick lookup
        company_dates = {holiday.date for holiday in company_holidays}

        # Check for deleted dates
        deleted_dates = set()
        deleted_holidays = Holiday.query.filter_by(
            holiday_type_id=holiday_type_obj.id,
            company_id=current_user.company_id,
            is_deleted=True  # Find all deleted holidays
        ).all()
        for holiday in deleted_holidays:
            deleted_dates.add(holiday.date)

        # Only add system-wide holidays that aren't already added or deleted
        system_holidays = Holiday.query.filter_by(
            holiday_type_id=holiday_type_obj.id,
            company_id=None
        ).order_by(Holiday.date).all()

        for holiday in system_holidays:
            if holiday.date not in company_dates and holiday.date not in deleted_dates:
                holidays.append(holiday)

        # Sort all holidays by date
        holidays.sort(key=lambda x: x.date)

    return render_template('manage_holidays.html',
                           holiday_type=holiday_type,
                           holidays=holidays,
                           success_message=success_message)


@occupancy_bp.route('/add_holiday', methods=['POST'])
@login_required
def add_holiday():
    if request.method == 'POST':
        name = request.form['name']
        date_str = request.form['date']
        holiday_type = request.form['holiday_type']

        # Convert date string to date object
        holiday_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        # Determine the holiday type ID
        if holiday_type == 'public':
            type_name = "Malaysia Public Holiday"
        elif holiday_type == 'school':
            type_name = "Malaysia School Holiday"
        else:
            type_name = "Custom Holiday"

        # Get or create the holiday type
        holiday_type_obj = HolidayType.query.filter_by(name=type_name).first()
        if not holiday_type_obj:
            if holiday_type == 'public':
                color = "#4CAF50"  # Green
            elif holiday_type == 'school':
                color = "#2196F3"  # Blue
            else:
                color = "#9C27B0"  # Purple

            holiday_type_obj = HolidayType(name=type_name, color=color, is_system=True)
            db.session.add(holiday_type_obj)
            db.session.commit()

        # Always create company-specific holidays
        company_id = current_user.company_id

        # Check if this holiday already exists for this company
        existing_holiday = Holiday.query.filter_by(
            date=holiday_date,
            holiday_type_id=holiday_type_obj.id,
            company_id=company_id
        ).first()

        if existing_holiday:
            success_message = f"This {holiday_type} holiday already exists for this date."
        else:
            # Create the holiday (company-specific)
            new_holiday = Holiday(
                name=name,
                date=holiday_date,
                holiday_type_id=holiday_type_obj.id,
                company_id=company_id,
                is_recurring=False,  # Set to false by default
                is_deleted=False
            )

            db.session.add(new_holiday)
            db.session.commit()

            if holiday_type == 'public':
                success_message = "Public holiday added successfully"
            elif holiday_type == 'school':
                success_message = "School holiday added successfully"
            else:
                success_message = "Custom day added successfully"

        return redirect(url_for('occupancy.manage_holidays',
                                type=holiday_type,
                                success_message=success_message))


@occupancy_bp.route('/delete_holiday/<int:id>', methods=['POST'])
@login_required
def delete_holiday(id):
    holiday = Holiday.query.get_or_404(id)

    # Determine the holiday type for redirect
    holiday_type_name = holiday.holiday_type.name
    if "Public" in holiday_type_name:
        redirect_type = 'public'
    elif "School" in holiday_type_name:
        redirect_type = 'school'
    else:
        redirect_type = 'custom'

    # Special handling for system-wide holidays
    if holiday.company_id is None:
        # This is a system-wide holiday, so create a "deleted" marker for this company
        deleted_marker = Holiday(
            name=holiday.name,  # No DELETED_ prefix
            date=holiday.date,
            holiday_type_id=holiday.holiday_type_id,
            company_id=current_user.company_id,
            is_recurring=False,
            is_deleted=True  # Mark as deleted
        )
        db.session.add(deleted_marker)
        success_message = "Holiday removed from your calendar"
    else:
        # This is a company-specific holiday
        # Check if user has permission to delete this holiday
        if holiday.company_id != current_user.company_id:
            flash('You do not have permission to delete this holiday', 'danger')
            return redirect(url_for('occupancy.manage_holidays', type=redirect_type))

        # Delete the holiday
        db.session.delete(holiday)
        success_message = "Holiday deleted successfully"

    db.session.commit()

    return redirect(url_for('occupancy.manage_holidays',
                            type=redirect_type,
                            success_message=success_message))