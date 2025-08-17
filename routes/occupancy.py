from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Unit, BookingForm, Holiday, HolidayType, CompanyHolidayPreference, CompanyHolidayOverride
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

    # Set Monday as first day of week (0 = Monday, 6 = Sunday)
    calendar.setfirstweekday(0)  # This ensures Monday is the first day

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
        return jsonify({
            "occupancy": {},
            "total_units": 0,
            "holidays": {}
        })

    # Filter for ACTIVE units only
    accessible_active_units = Unit.query.filter(
        Unit.id.in_(accessible_unit_ids),
        Unit.is_occupied == True
    ).all()

    accessible_active_unit_ids = [unit.id for unit in accessible_active_units]

    if not accessible_active_unit_ids:
        return jsonify({
            "occupancy": {},
            "total_units": 0,
            "holidays": {}
        })

    # Get the first and last day of the month
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    # Get bookings that overlap with this month for accessible ACTIVE units only - EXCLUDE CANCELLED
    bookings = BookingForm.query.filter(
        BookingForm.company_id == current_user.company_id,
        BookingForm.unit_id.in_(accessible_active_unit_ids),
        BookingForm.is_cancelled != True,  # EXCLUDE CANCELLED BOOKINGS
        BookingForm.check_in_date <= last_day,
        BookingForm.check_out_date > first_day
    ).all()

    # Calculate occupancy for each day of the month
    import calendar as cal_module
    days_in_month = cal_module.monthrange(year, month)[1]
    occupancy_data = {day: 0 for day in range(1, days_in_month + 1)}

    # Count occupied units for each day
    for booking in bookings:
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            if booking.check_in_date <= current_date < booking.check_out_date:
                occupancy_data[day] += 1

    # Get total accessible ACTIVE units
    total_units = len(accessible_active_unit_ids)

    # FIXED: Get holidays with better type detection
    holiday_data = {}

    # Country flag mapping
    country_flags = {
        'Malaysia': '🇲🇾',
        'Singapore': '🇸🇬',
        'Indonesia': '🇮🇩',
        'China': '🇨🇳',
        'Korea': '🇰🇷',
        'Japan': '🇯🇵'
    }

    print(f"DEBUG: Getting holidays for company {current_user.company_id} for {year}-{month}")

    # FIXED: Get ALL holiday types that contain country names (more flexible approach)
    all_holiday_types = HolidayType.query.all()
    country_holiday_type_ids = []

    for ht in all_holiday_types:
        for country in country_flags.keys():
            if country in ht.name:
                country_holiday_type_ids.append(ht.id)
                print(f"DEBUG: Found holiday type: {ht.name} (ID: {ht.id})")
                break

    print(f"DEBUG: All country holiday type IDs: {country_holiday_type_ids}")

    # Get enabled holiday types for this company
    enabled_preferences = CompanyHolidayPreference.query.filter_by(
        company_id=current_user.company_id,
        is_enabled=True
    ).all()

    enabled_holiday_type_ids = [pref.holiday_type_id for pref in enabled_preferences]
    print(f"DEBUG: Company enabled holiday type IDs: {enabled_holiday_type_ids}")

    # FIXED: Use intersection to get both country-related AND enabled types
    final_holiday_type_ids = list(set(country_holiday_type_ids) & set(enabled_holiday_type_ids))
    print(f"DEBUG: Final holiday type IDs to query: {final_holiday_type_ids}")

    if final_holiday_type_ids:
        # Get system holidays for enabled countries
        system_holidays = Holiday.query.filter(
            Holiday.holiday_type_id.in_(final_holiday_type_ids),
            Holiday.company_id.is_(None),  # System holidays only
            Holiday.date.between(first_day, last_day),
            Holiday.is_active == True
        ).all()

        print(f"DEBUG: Found {len(system_holidays)} system holidays")
        for holiday in system_holidays:
            print(f"  - {holiday.date}: {holiday.name} ({holiday.holiday_type.name})")

        # Get company overrides for these holidays
        overrides = {}
        if system_holidays:
            holiday_ids = [h.id for h in system_holidays]
            company_overrides = CompanyHolidayOverride.query.filter(
                CompanyHolidayOverride.company_id == current_user.company_id,
                CompanyHolidayOverride.holiday_id.in_(holiday_ids)
            ).all()

            for override in company_overrides:
                overrides[override.holiday_id] = override.is_enabled
                print(f"DEBUG: Override for holiday {override.holiday_id}: {override.is_enabled}")

        # Process system holidays
        for holiday in system_holidays:
            # Check if this holiday is enabled for this company (default: enabled)
            is_enabled = overrides.get(holiday.id, True)

            print(f"DEBUG: Processing holiday {holiday.name} on {holiday.date}: enabled={is_enabled}")

            if not is_enabled:
                print(f"DEBUG: Skipping disabled holiday: {holiday.name}")
                continue

            day = holiday.date.day
            if day not in holiday_data:
                holiday_data[day] = []

            # Extract country from holiday type name and get flag
            holiday_type_name = holiday.holiday_type.name
            country_flag = ''
            for country, flag in country_flags.items():
                if country in holiday_type_name:
                    country_flag = flag
                    break

            # Determine holiday type for display
            if "Public" in holiday_type_name:
                type_class = "public"
            elif "School" in holiday_type_name:
                type_class = "school"
            else:
                type_class = "custom"

            print(f"DEBUG: Adding holiday to day {day}: {country_flag} {holiday.name} (type: {type_class})")

            holiday_data[day].append({
                "name": f"{country_flag} {holiday.name}",
                "type": type_class,
                "color": holiday.holiday_type.color
            })

    # Also get company-specific custom holidays
    custom_holiday_types = HolidayType.query.filter_by(name="Custom Holiday").all()

    for holiday_type in custom_holiday_types:
        company_holidays = Holiday.query.filter(
            Holiday.holiday_type_id == holiday_type.id,
            Holiday.company_id == current_user.company_id,
            Holiday.is_deleted == False,
            Holiday.is_active == True,
            Holiday.date.between(first_day, last_day)
        ).all()

        print(f"DEBUG: Found {len(company_holidays)} custom holidays")

        for holiday in company_holidays:
            day = holiday.date.day
            if day not in holiday_data:
                holiday_data[day] = []

            holiday_data[day].append({
                "name": holiday.name,
                "type": "custom",
                "color": holiday_type.color
            })

    print(f"DEBUG: Final holiday_data: {holiday_data}")

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


@occupancy_bp.route('/toggle_country_calendar', methods=['POST'])
@login_required
def toggle_country_calendar():
    """Toggle a country's holiday calendar for the current company"""
    data = request.get_json()
    country = data.get('country')
    is_enabled = data.get('enabled', False)

    # FIXED: Determine the current page type from the referrer URL
    current_url = request.referrer or ''
    is_school_page = 'type=school' in current_url

    print(f"DEBUG: toggle_country_calendar - country: {country}, enabled: {is_enabled}, is_school_page: {is_school_page}")

    # FIXED: Map country names to the SPECIFIC holiday type based on the current page
    if is_school_page:
        country_mapping = {
            'malaysia': 'Malaysia School Holiday',
            'singapore': 'Singapore School Holiday',
            'indonesia': 'Indonesia School Holiday',
            'china': 'China School Holiday',
            'korea': 'Korea School Holiday',
            'japan': 'Japan School Holiday'
        }
    else:
        country_mapping = {
            'malaysia': 'Malaysia Public Holiday',
            'singapore': 'Singapore Public Holiday',
            'indonesia': 'Indonesia Public Holiday',
            'china': 'China Public Holiday',
            'korea': 'Korea Public Holiday',
            'japan': 'Japan Public Holiday'
        }

    holiday_type_name = country_mapping.get(country.lower())
    if not holiday_type_name:
        print(f"DEBUG: Invalid country: {country}")
        return jsonify({'success': False, 'message': 'Invalid country'})

    print(f"DEBUG: Looking for holiday type: {holiday_type_name}")

    # Get the holiday type
    holiday_type = HolidayType.query.filter_by(name=holiday_type_name).first()
    if not holiday_type:
        print(f"DEBUG: Holiday type not found: {holiday_type_name}")
        return jsonify({'success': False, 'message': 'Holiday type not found'})

    print(f"DEBUG: Found holiday type: {holiday_type.name} (ID: {holiday_type.id})")

    # Get or create company holiday preference for THIS SPECIFIC holiday type
    preference = CompanyHolidayPreference.query.filter_by(
        company_id=current_user.company_id,
        holiday_type_id=holiday_type.id
    ).first()

    if not preference:
        preference = CompanyHolidayPreference(
            company_id=current_user.company_id,
            holiday_type_id=holiday_type.id,
            is_enabled=is_enabled
        )
        db.session.add(preference)
        print(f"DEBUG: Created new preference for {holiday_type.name}: {is_enabled}")
    else:
        preference.is_enabled = is_enabled
        print(f"DEBUG: Updated existing preference for {holiday_type.name}: {is_enabled}")

    db.session.commit()

    holiday_category = "school" if is_school_page else "public"
    return jsonify({
        'success': True,
        'message': f'{country.title()} {holiday_category} calendar {"enabled" if is_enabled else "disabled"}'
    })


@occupancy_bp.route('/get_country_holidays/<country>')
@occupancy_bp.route('/get_country_holidays/<country>/<holiday_type>')
@login_required
def get_country_holidays(country, holiday_type='public'):
    """Get holidays for a specific country - UPDATED VERSION"""

    # Map country names to holiday type names
    if holiday_type == 'school':
        country_mapping = {
            'malaysia': 'Malaysia School Holiday',
            'singapore': 'Singapore School Holiday',
            'indonesia': 'Indonesia School Holiday',
            'china': 'China School Holiday',
            'korea': 'Korea School Holiday',
            'japan': 'Japan School Holiday'
        }
    else:
        country_mapping = {
            'malaysia': 'Malaysia Public Holiday',
            'singapore': 'Singapore Public Holiday',
            'indonesia': 'Indonesia Public Holiday',
            'china': 'China Public Holiday',
            'korea': 'Korea Public Holiday',
            'japan': 'Japan Public Holiday'
        }

    # Map country names to emoji flags
    country_flags = {
        'malaysia': '🇲🇾',
        'singapore': '🇸🇬',
        'indonesia': '🇮🇩',
        'china': '🇨🇳',
        'korea': '🇰🇷',
        'japan': '🇯🇵'
    }

    holiday_type_name = country_mapping.get(country.lower())
    if not holiday_type_name:
        return jsonify({'success': False, 'message': 'Invalid country'})

    # Get the holiday type
    holiday_type = HolidayType.query.filter_by(name=holiday_type_name).first()
    if not holiday_type:
        return jsonify({'success': False, 'message': 'Holiday type not found'})

    # Get all system holidays for this country
    holidays = Holiday.query.filter_by(
        holiday_type_id=holiday_type.id,
        company_id=None  # System holidays only
    ).order_by(Holiday.date).all()

    # Get company overrides for these holidays
    overrides = {}
    if holidays:
        holiday_ids = [h.id for h in holidays]
        company_overrides = CompanyHolidayOverride.query.filter(
            CompanyHolidayOverride.company_id == current_user.company_id,
            CompanyHolidayOverride.holiday_id.in_(holiday_ids)
        ).all()

        for override in company_overrides:
            overrides[override.holiday_id] = override.is_enabled

    # Format holidays data - UPDATED to include day_of_week and states
    holidays_data = []
    for holiday in holidays:
        # Default to enabled unless specifically disabled
        is_enabled = overrides.get(holiday.id, True)

        # Calculate day of week if not stored
        day_of_week = holiday.day_of_week
        if not day_of_week:
            day_of_week = holiday.date.strftime('%A')

        holidays_data.append({
            'id': holiday.id,
            'date': holiday.date.strftime('%Y-%m-%d'),
            'name': holiday.name,
            'day_of_week': day_of_week,  # ADDED: Day of week
            'states': holiday.states or '',  # ADDED: States/regions
            'active': is_enabled,
            'flag': country_flags.get(country.lower(), '')
        })

    return jsonify({
        'success': True,
        'holidays': holidays_data,
        'country': country.title(),
        'flag': country_flags.get(country.lower(), '')
    })


@occupancy_bp.route('/toggle_holiday_date', methods=['POST'])
@login_required
def toggle_holiday_date():
    """Toggle a specific holiday date for the current company"""
    data = request.get_json()
    holiday_id = data.get('holiday_id')
    is_enabled = data.get('enabled', True)

    # Get the holiday
    holiday = Holiday.query.get_or_404(holiday_id)

    # Get or create company holiday override
    override = CompanyHolidayOverride.query.filter_by(
        company_id=current_user.company_id,
        holiday_id=holiday_id
    ).first()

    if not override:
        override = CompanyHolidayOverride(
            company_id=current_user.company_id,
            holiday_id=holiday_id,
            is_enabled=is_enabled
        )
        db.session.add(override)
    else:
        override.is_enabled = is_enabled

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Holiday "{holiday.name}" {"enabled" if is_enabled else "disabled"}'
    })


@occupancy_bp.route('/get_company_holiday_preferences')
@login_required
def get_company_holiday_preferences():
    """Get the current company's holiday calendar preferences"""

    # FIXED: Determine what type of holidays to check based on referrer
    current_url = request.referrer or ''
    is_school_page = 'type=school' in current_url

    print(f"DEBUG: get_company_holiday_preferences - is_school_page: {is_school_page}")

    # Get all enabled holiday preferences for this company
    preferences = CompanyHolidayPreference.query.filter_by(
        company_id=current_user.company_id,
        is_enabled=True
    ).all()

    enabled_countries = []
    for pref in preferences:
        holiday_type_name = pref.holiday_type.name
        print(f"DEBUG: Checking preference: {holiday_type_name}")

        # FIXED: Only include countries that match the current page type
        if is_school_page and 'School' in holiday_type_name:
            # Extract country name from school holiday type
            if 'Malaysia' in holiday_type_name:
                enabled_countries.append('malaysia')
            elif 'Singapore' in holiday_type_name:
                enabled_countries.append('singapore')
            elif 'Indonesia' in holiday_type_name:
                enabled_countries.append('indonesia')
            elif 'China' in holiday_type_name:
                enabled_countries.append('china')
            elif 'Korea' in holiday_type_name:
                enabled_countries.append('korea')
            elif 'Japan' in holiday_type_name:
                enabled_countries.append('japan')
        elif not is_school_page and 'Public' in holiday_type_name:
            # Extract country name from public holiday type
            if 'Malaysia' in holiday_type_name:
                enabled_countries.append('malaysia')
            elif 'Singapore' in holiday_type_name:
                enabled_countries.append('singapore')
            elif 'Indonesia' in holiday_type_name:
                enabled_countries.append('indonesia')
            elif 'China' in holiday_type_name:
                enabled_countries.append('china')
            elif 'Korea' in holiday_type_name:
                enabled_countries.append('korea')
            elif 'Japan' in holiday_type_name:
                enabled_countries.append('japan')

    print(f"DEBUG: Enabled countries for {'school' if is_school_page else 'public'}: {enabled_countries}")

    return jsonify({
        'success': True,
        'enabled_countries': list(set(enabled_countries))  # Remove duplicates
    })