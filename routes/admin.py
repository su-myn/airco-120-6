from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from functools import wraps
from models import db, User, Company, Role, Unit, Issue, Holiday, HolidayType, BookingForm, Category, ReportedBy, Priority, Status, Type, IssueItem, Contact, ExpenseData, CompanyHolidayOverride
import csv
import io
from datetime import datetime, date
from werkzeug.utils import secure_filename


from datetime import datetime
import csv
import io
from functools import wraps

from app import bcrypt
import csv
import io
from flask import make_response, request, jsonify
from datetime import datetime, date
import tempfile
import os

admin_bp = Blueprint('admin', __name__)

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You do not have permission to access the admin panel.', 'danger')
            return redirect(url_for('dashboard.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/')
@login_required
@admin_required
def admin_dashboard():
    users = User.query.all()
    companies = Company.query.all()
    roles = Role.query.all()
    units = Unit.query.all()
    issues = Issue.query.all()

    # Get count of each type by company
    company_stats = []
    for company in companies:
        company_users = User.query.filter_by(company_id=company.id).count()
        company_issues = Issue.query.filter_by(company_id=company.id).count()
        company_units = Unit.query.filter_by(company_id=company.id).count()

        company_stats.append({
            'name': company.name,
            'users': company_users,
            'issues': company_issues,
            'units': company_units
        })

    return render_template('admin/dashboard.html',
                           users=users,
                           companies=companies,
                           roles=roles,
                           issues=issues,
                           units=units,
                           company_stats=company_stats)

# Admin routes for units
@admin_bp.route('/units')
@login_required
@admin_required
def admin_units():
    units = Unit.query.all()
    return render_template('admin/units.html', units=units)

@admin_bp.route('/edit_unit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_unit(id):
    unit = Unit.query.get_or_404(id)
    companies = Company.query.all()

    if request.method == 'POST':
        unit.unit_number = request.form['unit_number']
        unit.description = request.form['description']
        unit.floor = request.form['floor'] or None
        unit.building = request.form['building']
        unit.company_id = request.form['company_id']
        unit.is_occupied = 'is_occupied' in request.form

        # Update new fields
        toilet_count = request.form.get('toilet_count') or None
        towel_count = request.form.get('towel_count') or None
        max_pax = request.form.get('max_pax') or None

        # Convert to integers if not None
        if toilet_count:
            unit.toilet_count = int(toilet_count)
        else:
            unit.toilet_count = None

        if towel_count:
            unit.towel_count = int(towel_count)
        else:
            unit.towel_count = None

        if max_pax:
            unit.max_pax = int(max_pax)
        else:
            unit.max_pax = None

        db.session.commit()
        flash('Unit updated successfully', 'success')
        return redirect(url_for('admin.admin_units'))

    return render_template('admin/edit_unit.html', unit=unit, companies=companies)

@admin_bp.route('/delete_unit/<int:id>')
@login_required
@admin_required
def admin_delete_unit(id):
    unit = Unit.query.get_or_404(id)

    # Check if unit is in use
    if unit.complaints or unit.repairs or unit.replacements:
        flash('Cannot delete unit that is referenced by complaints, repairs, or replacements', 'danger')
        return redirect(url_for('admin.admin_units'))

    db.session.delete(unit)
    db.session.commit()

    flash('Unit deleted successfully', 'success')
    return redirect(url_for('admin.admin_units'))


@admin_bp.route('/add_unit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_unit():
    companies = Company.query.all()

    if request.method == 'POST':
        unit_number = request.form['unit_number']
        building = request.form.get('building')
        floor = request.form.get('floor')
        description = request.form.get('description')
        company_id = request.form['company_id']
        is_occupied = 'is_occupied' in request.form

        # Handle optional numeric fields
        toilet_count = request.form.get('toilet_count') or None
        towel_count = request.form.get('towel_count') or None
        max_pax = request.form.get('max_pax') or None

        # Convert to integers if not None
        if toilet_count:
            toilet_count = int(toilet_count)
        if towel_count:
            towel_count = int(towel_count)
        if max_pax:
            max_pax = int(max_pax)
        if floor:
            floor = int(floor)

        # Check if unit number already exists in this company
        existing_unit = Unit.query.filter_by(unit_number=unit_number, company_id=company_id).first()
        if existing_unit:
            flash('This unit number already exists in the selected company', 'danger')
            return render_template('admin/add_unit.html', companies=companies)

        new_unit = Unit(
            unit_number=unit_number,
            building=building,
            floor=floor,
            description=description,
            company_id=company_id,
            is_occupied=is_occupied,
            toilet_count=toilet_count,
            towel_count=towel_count,
            max_pax=max_pax
        )

        db.session.add(new_unit)
        db.session.commit()

        flash('Unit added successfully', 'success')
        return redirect(url_for('admin.admin_units'))

    return render_template('admin/add_unit.html', companies=companies)


# User management routes
@admin_bp.route('/users')
@login_required
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)


@admin_bp.route('/add_user', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_user():
    # Get all companies and roles for the form
    companies = Company.query.all()
    roles = Role.query.all()

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        company_id = request.form['company_id']
        role_id = request.form['role_id']
        is_cleaner = 'is_cleaner' in request.form  # Check if is_cleaner checkbox is checked

        # Check if user already exists
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email already registered', 'danger')
            return redirect(url_for('admin.admin_add_user'))

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # Create new user without account_type_id
        new_user = User(
            name=name,
            email=email,
            password=hashed_password,
            company_id=company_id,
            role_id=role_id,
            is_cleaner=is_cleaner
        )

        try:
            db.session.add(new_user)
            db.session.commit()
            flash('User added successfully', 'success')
            return redirect(url_for('admin.admin_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding user: {str(e)}', 'danger')
            return redirect(url_for('admin.admin_add_user'))

    return render_template('admin/add_user.html', companies=companies, roles=roles)


@admin_bp.route('/edit_user/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_user(id):
    user = User.query.get_or_404(id)
    companies = Company.query.all()
    roles = Role.query.all()

    if request.method == 'POST':
        user.name = request.form['name']
        user.email = request.form['email']
        user.company_id = request.form['company_id']
        user.role_id = request.form['role_id']
        user.is_cleaner = 'is_cleaner' in request.form  # Update is_cleaner field

        # Only update password if provided
        if request.form['password'].strip():
            user.password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')

        db.session.commit()
        flash('User updated successfully', 'success')
        return redirect(url_for('admin.admin_users'))

    return render_template('admin/edit_user.html', user=user, companies=companies, roles=roles)

@admin_bp.route('/delete_user/<int:id>')
@login_required
@admin_required
def admin_delete_user(id):
    if id == current_user.id:
        flash('You cannot delete your own account', 'danger')
        return redirect(url_for('admin.admin_users'))

    user = User.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()

    flash('User deleted successfully', 'success')
    return redirect(url_for('admin.admin_users'))

# Company routes
@admin_bp.route('/companies')
@login_required
@admin_required
def admin_companies():
    companies = Company.query.all()
    return render_template('admin/companies.html', companies=companies)


@admin_bp.route('/add_company', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_company():
    if request.method == 'POST':
        name = request.form['name']
        max_units = request.form.get('max_units', 20)
        max_manager_users = request.form.get('max_manager_users', 1)
        max_staff_users = request.form.get('max_staff_users', 1)
        max_cleaner_users = request.form.get('max_cleaner_users', 2)

        # Validate inputs
        try:
            max_units = int(max_units)
            max_manager_users = int(max_manager_users)
            max_staff_users = int(max_staff_users)
            max_cleaner_users = int(max_cleaner_users)

            if max_units < 15 or max_units > 1000:
                flash('Unit limit must be between 15 and 1000', 'danger')
                return render_template('admin/add_company.html')

            if max_manager_users < 1 or max_staff_users < 0 or max_cleaner_users < 0:
                flash('Manager limit must be at least 1, other limits must be non-negative', 'danger')
                return render_template('admin/add_company.html')

        except ValueError:
            flash('Invalid values provided', 'danger')
            return render_template('admin/add_company.html')

        # Check if company already exists
        company = Company.query.filter_by(name=name).first()
        if company:
            flash('Company already exists', 'danger')
            return redirect(url_for('admin.admin_add_company'))

        new_company = Company(
            name=name,
            max_units=max_units,
            max_manager_users=max_manager_users,
            max_staff_users=max_staff_users,
            max_cleaner_users=max_cleaner_users
        )
        db.session.add(new_company)
        db.session.commit()

        flash('Company added successfully', 'success')
        return redirect(url_for('admin.admin_companies'))

    return render_template('admin/add_company.html')


@admin_bp.route('/edit_company/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_company(id):
    company = Company.query.get_or_404(id)

    if request.method == 'POST':
        company.name = request.form['name']
        max_units = request.form.get('max_units', company.max_units)
        max_manager_users = request.form.get('max_manager_users', company.max_manager_users)
        max_staff_users = request.form.get('max_staff_users', company.max_staff_users)
        max_cleaner_users = request.form.get('max_cleaner_users', company.max_cleaner_users)

        # Validate inputs
        try:
            max_units = int(max_units)
            max_manager_users = int(max_manager_users)
            max_staff_users = int(max_staff_users)
            max_cleaner_users = int(max_cleaner_users)

            if max_units < 15 or max_units > 1000:
                flash('Unit limit must be between 15 and 1000', 'danger')
                return render_template('admin/edit_company.html', company=company)

            if max_manager_users < 1:
                flash('Manager limit must be at least 1', 'danger')
                return render_template('admin/edit_company.html', company=company)

        except ValueError:
            flash('Invalid values provided', 'danger')
            return render_template('admin/edit_company.html', company=company)

        # Check if reducing limits below current user count
        current_units = Unit.query.filter_by(company_id=company.id).count()
        if max_units < current_units:
            flash(f'Cannot set unit limit to {max_units}. Company currently has {current_units} units.', 'danger')
            return render_template('admin/edit_company.html', company=company)

        # Check user limits
        current_managers = company.get_user_count_by_role('Manager')
        current_staff = company.get_user_count_by_role('Staff')
        current_cleaners = company.get_user_count_by_role('Cleaner')

        if max_manager_users < current_managers:
            flash(
                f'Cannot set Manager limit to {max_manager_users}. Company currently has {current_managers} Managers.',
                'danger')
            return render_template('admin/edit_company.html', company=company)

        if max_staff_users < current_staff:
            flash(f'Cannot set Staff limit to {max_staff_users}. Company currently has {current_staff} Staff.',
                  'danger')
            return render_template('admin/edit_company.html', company=company)

        if max_cleaner_users < current_cleaners:
            flash(
                f'Cannot set Cleaner limit to {max_cleaner_users}. Company currently has {current_cleaners} Cleaners.',
                'danger')
            return render_template('admin/edit_company.html', company=company)

        # Update company
        company.max_units = max_units
        company.max_manager_users = max_manager_users
        company.max_staff_users = max_staff_users
        company.max_cleaner_users = max_cleaner_users

        db.session.commit()
        flash('Company updated successfully', 'success')
        return redirect(url_for('admin.admin_companies'))

    return render_template('admin/edit_company.html', company=company)


@admin_bp.route('/delete_company/<int:id>')
@login_required
@admin_required
def admin_delete_company(id):
    company = Company.query.get_or_404(id)

    # Check if company has users or units
    if company.users or company.units:
        flash('Cannot delete company with existing users or units', 'danger')
        return redirect(url_for('admin.admin_companies'))

    db.session.delete(company)
    db.session.commit()

    flash('Company deleted successfully', 'success')
    return redirect(url_for('admin.admin_companies'))

# Role routes
@admin_bp.route('/roles')
@login_required
@admin_required
def admin_roles():
    roles = Role.query.all()
    return render_template('admin/roles.html', roles=roles)

@admin_bp.route('/add_role', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_role():
    if request.method == 'POST':
        name = request.form['name']

        # Check if role already exists
        role = Role.query.filter_by(name=name).first()
        if role:
            flash('Role already exists', 'danger')
            return redirect(url_for('admin.admin_add_role'))

        # Create new role with permissions
        new_role = Role(
            name=name,
            can_view_issues='can_view_issues' in request.form,
            can_manage_issues='can_manage_issues' in request.form,
            can_view_bookings='can_view_bookings' in request.form,
            can_manage_bookings='can_manage_bookings' in request.form,
            can_view_calendar='can_view_calendar' in request.form,
            can_manage_calendar='can_manage_calendar' in request.form,
            can_view_occupancy='can_view_occupancy' in request.form,
            can_manage_occupancy='can_manage_occupancy' in request.form,
            can_view_expenses='can_view_expenses' in request.form,
            can_manage_expenses='can_manage_expenses' in request.form,
            can_view_contacts='can_view_contacts' in request.form,
            can_manage_contacts='can_manage_contacts' in request.form,
            can_view_analytics='can_view_analytics' in request.form,
            can_manage_analytics='can_manage_analytics' in request.form,
            can_view_units='can_view_units' in request.form,
            can_manage_units='can_manage_units' in request.form,
            can_view_manage_cleaners='can_view_manage_cleaners' in request.form,
            can_manage_manage_cleaners='can_manage_manage_cleaners' in request.form,
            can_view_jadual_pembersihan='can_view_jadual_pembersihan' in request.form,
            can_manage_jadual_pembersihan='can_manage_jadual_pembersihan' in request.form,
            is_admin='is_admin' in request.form,
            can_manage_users='can_manage_users' in request.form
        )

        db.session.add(new_role)
        db.session.commit()

        flash('Role added successfully', 'success')
        return redirect(url_for('admin.admin_roles'))

    return render_template('admin/add_role.html')

@admin_bp.route('/edit_role/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_role(id):
    role = Role.query.get_or_404(id)

    if request.method == 'POST':
        role.name = request.form['name']

        # Update permissions

        role.can_view_issues = 'can_view_issues' in request.form
        role.can_manage_issues = 'can_manage_issues' in request.form
        role.can_view_bookings = 'can_view_bookings' in request.form
        role.can_manage_bookings = 'can_manage_bookings' in request.form
        role.can_view_calendar = 'can_view_calendar' in request.form
        role.can_manage_calendar = 'can_manage_calendar' in request.form
        role.can_view_occupancy = 'can_view_occupancy' in request.form
        role.can_manage_occupancy = 'can_manage_occupancy' in request.form
        role.can_view_expenses = 'can_view_expenses' in request.form
        role.can_manage_expenses = 'can_manage_expenses' in request.form
        role.can_view_contacts = 'can_view_contacts' in request.form
        role.can_manage_contacts = 'can_manage_contacts' in request.form
        role.can_view_analytics = 'can_view_analytics' in request.form
        role.can_manage_analytics = 'can_manage_analytics' in request.form
        role.can_view_units = 'can_view_units' in request.form
        role.can_manage_units = 'can_manage_units' in request.form
        role.can_view_manage_cleaners = 'can_view_manage_cleaners' in request.form
        role.can_manage_manage_cleaners = 'can_manage_manage_cleaners' in request.form
        role.can_view_jadual_pembersihan = 'can_view_jadual_pembersihan' in request.form
        role.can_manage_jadual_pembersihan = 'can_manage_jadual_pembersihan' in request.form
        role.is_admin = 'is_admin' in request.form
        role.can_manage_users = 'can_manage_users' in request.form

        db.session.commit()
        flash('Role updated successfully', 'success')
        return redirect(url_for('admin.admin_roles'))

    return render_template('admin/edit_role.html', role=role)

@admin_bp.route('/delete_role/<int:id>')
@login_required
@admin_required
def admin_delete_role(id):
    role = Role.query.get_or_404(id)

    # Check if role has users
    if role.users:
        flash('Cannot delete role with existing users', 'danger')
        return redirect(url_for('admin.admin_roles'))

    db.session.delete(role)
    db.session.commit()

    flash('Role deleted successfully', 'success')
    return redirect(url_for('admin.admin_roles'))



# Holiday management routes for admin.py

@admin_bp.route('/create_default_holiday_types')
@login_required
@admin_required
def create_default_holiday_types():
    """Create default holiday types for different countries"""
    try:
        default_types = [
            # Public Holiday Types
            {"name": "Malaysia Public Holiday", "color": "#4CAF50", "is_system": True},
            {"name": "Singapore Public Holiday", "color": "#4CAF50", "is_system": True},
            {"name": "Indonesia Public Holiday", "color": "#4CAF50", "is_system": True},
            {"name": "China Public Holiday", "color": "#4CAF50", "is_system": True},
            {"name": "Korea Public Holiday", "color": "#4CAF50", "is_system": True},
            {"name": "Japan Public Holiday", "color": "#4CAF50", "is_system": True},

            # School Holiday Types
            {"name": "Malaysia School Holiday", "color": "#2196F3", "is_system": True},
            {"name": "Singapore School Holiday", "color": "#2196F3", "is_system": True},
            {"name": "Indonesia School Holiday", "color": "#2196F3", "is_system": True},
            {"name": "China School Holiday", "color": "#2196F3", "is_system": True},
            {"name": "Korea School Holiday", "color": "#2196F3", "is_system": True},
            {"name": "Japan School Holiday", "color": "#2196F3", "is_system": True},

            # Custom
            {"name": "Custom Holiday", "color": "#9C27B0", "is_system": True}
        ]

        created_count = 0

        for type_data in default_types:
            existing_type = HolidayType.query.filter_by(name=type_data["name"]).first()
            if not existing_type:
                holiday_type = HolidayType(
                    name=type_data["name"],
                    color=type_data["color"],
                    is_system=type_data["is_system"]
                )
                db.session.add(holiday_type)
                created_count += 1

        if created_count > 0:
            db.session.commit()
            flash(f'{created_count} default holiday types created successfully', 'success')
        else:
            flash('All default holiday types already exist', 'info')

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating holiday types: {str(e)}', 'danger')
        print(f"Error creating default holiday types: {e}")

    return redirect(url_for('admin.admin_holidays'))


@admin_bp.route('/system_holidays')
@login_required
@admin_required
def system_holidays():
    # Based on your Image 2, get specific holiday types by their IDs
    # We know these exist: IDs 1,2,4,5,6,7,8,9,10...

    # Get holiday types that are Public or School holidays
    # Use specific names we can see from your admin_holidays page
    holiday_type_names = [
        'Malaysia Public Holiday',
        'Singapore Public Holiday',
        'Indonesia Public Holiday',
        'China Public Holiday',
        'Korea Public Holiday',
        'Japan Public Holiday',
        'Malaysia School Holiday',
        'Singapore School Holiday',
        'Indonesia School Holiday',
        'China School Holiday',
        'Korea School Holiday',
        'Japan School Holiday'
    ]

    holiday_types = HolidayType.query.filter(
        HolidayType.name.in_(holiday_type_names)
    ).order_by(HolidayType.name).all()

    # Debug print
    print(f"Found {len(holiday_types)} holiday types:")
    for ht in holiday_types:
        print(f"  - ID {ht.id}: {ht.name}")

    # Get all system holidays (company_id is None)
    public_holidays = Holiday.query.join(HolidayType).filter(
        Holiday.company_id.is_(None),
        HolidayType.name.contains('Public Holiday')
    ).order_by(Holiday.date).all()

    school_holidays = Holiday.query.join(HolidayType).filter(
        Holiday.company_id.is_(None),
        HolidayType.name.contains('School Holiday')
    ).order_by(Holiday.date).all()

    return render_template('admin/system_holidays.html',
                           holiday_types=holiday_types,
                           public_holidays=public_holidays,
                           school_holidays=school_holidays)


@admin_bp.route('/add_system_holiday', methods=['POST'])
@login_required
@admin_required
def add_system_holiday():
    """Add a new system-wide holiday - ALLOWS MULTIPLE HOLIDAYS PER DATE/TYPE"""
    try:
        holiday_type_id = request.form.get('holiday_type_id')
        date_str = request.form.get('date')
        name = request.form.get('name')
        states = request.form.get('states', '').strip()
        is_recurring = 'is_recurring' in request.form

        # Validate required fields
        if not all([holiday_type_id, date_str, name]):
            flash('All required fields must be filled', 'danger')
            return redirect(url_for('admin.admin_holidays'))

        # Parse date
        try:
            holiday_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format', 'danger')
            return redirect(url_for('admin.admin_holidays'))

        # REMOVED: Check for existing holiday - now allows multiple holidays per date/type
        # This allows multiple holidays for the same country/type/date

        # Create new system holiday
        new_holiday = Holiday(
            name=name,
            date=holiday_date,
            holiday_type_id=holiday_type_id,
            company_id=None,  # System holiday
            is_recurring=is_recurring,
            is_deleted=False,
            day_of_week=holiday_date.strftime('%A'),
            states=states if states else None,
            is_active=True
        )

        db.session.add(new_holiday)
        db.session.commit()

        flash(f'System holiday "{name}" added successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error adding holiday: {str(e)}', 'danger')
        print(f"Error adding system holiday: {e}")

    return redirect(url_for('admin.admin_holidays'))


@admin_bp.route('/import_holidays', methods=['POST'])
@login_required
@admin_required
def import_holidays():
    """Import holidays from CSV file - FIXED VERSION - ALLOWS DUPLICATES"""
    try:
        # Check if file was uploaded
        if 'csv_file' not in request.files:
            flash('No file uploaded', 'danger')
            return redirect(url_for('admin.admin_holidays'))

        file = request.files['csv_file']

        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('admin.admin_holidays'))

        if not file.filename.lower().endswith('.csv'):
            flash('Please upload a CSV file', 'danger')
            return redirect(url_for('admin.admin_holidays'))

        # Get holiday type from form
        holiday_type_id = request.form.get('holiday_type_id')

        if not holiday_type_id:
            flash('Please select a holiday type for the import', 'danger')
            return redirect(url_for('admin.admin_holidays'))

        # Validate holiday type exists
        holiday_type = HolidayType.query.get(holiday_type_id)
        if not holiday_type:
            flash('Invalid holiday type selected', 'danger')
            return redirect(url_for('admin.admin_holidays'))

        # Read and parse CSV
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)

        # Expected columns
        required_columns = ['Date', 'Name']
        optional_columns = ['Day', 'States', 'Recurring']

        # Check if required columns exist
        if not all(col in csv_reader.fieldnames for col in required_columns):
            flash(f'CSV must contain columns: {", ".join(required_columns)}', 'danger')
            return redirect(url_for('admin.admin_holidays'))

        holidays_added = 0
        holidays_skipped = 0
        errors = []

        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 to account for header
            try:
                # Parse required fields
                date_str = row['Date'].strip()
                name = row['Name'].strip()

                if not date_str or not name:
                    errors.append(f"Row {row_num}: Missing required data")
                    continue

                # Parse date (try multiple formats)
                holiday_date = None
                date_formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d']

                for date_format in date_formats:
                    try:
                        holiday_date = datetime.strptime(date_str, date_format).date()
                        break
                    except ValueError:
                        continue

                if not holiday_date:
                    errors.append(f"Row {row_num}: Invalid date format '{date_str}'")
                    continue

                # Parse optional fields
                states = row.get('States', '').strip()
                recurring_str = row.get('Recurring', 'false').strip().lower()
                is_recurring = recurring_str in ['true', '1', 'yes', 'y']

                # REMOVED: Check if holiday already exists - now allows duplicates
                # The old code was:
                # existing_holiday = Holiday.query.filter_by(
                #     date=holiday_date,
                #     holiday_type_id=holiday_type_id,
                #     company_id=None  # System holiday
                # ).first()
                #
                # if existing_holiday:
                #     holidays_skipped += 1
                #     continue

                # Create new holiday (always, even if one exists)
                new_holiday = Holiday(
                    name=name,
                    date=holiday_date,
                    holiday_type_id=holiday_type_id,
                    company_id=None,  # System holiday
                    is_recurring=is_recurring,
                    is_deleted=False,
                    day_of_week=holiday_date.strftime('%A'),
                    states=states if states else None,
                    is_active=True
                )

                db.session.add(new_holiday)
                holidays_added += 1

            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
                continue

        # Commit all changes
        if holidays_added > 0:
            db.session.commit()

        # Create success message
        message_parts = []
        if holidays_added > 0:
            message_parts.append(f"{holidays_added} holiday(s) imported")
        if holidays_skipped > 0:
            message_parts.append(f"{holidays_skipped} holiday(s) skipped (already exist)")
        if errors:
            message_parts.append(f"{len(errors)} error(s)")

        if holidays_added > 0:
            flash(f"Import completed: {', '.join(message_parts)}", 'success')
        elif errors:
            flash(f"Import failed: {', '.join(message_parts)}", 'warning')
        else:
            flash("No holidays were imported", 'info')

        # Show first few errors if any
        if errors:
            for error in errors[:5]:  # Show first 5 errors
                flash(error, 'danger')
            if len(errors) > 5:
                flash(f"... and {len(errors) - 5} more errors", 'danger')

    except Exception as e:
        db.session.rollback()
        flash(f'Error importing holidays: {str(e)}', 'danger')
        print(f"Error importing holidays: {e}")
        import traceback
        traceback.print_exc()

    return redirect(url_for('admin.admin_holidays'))


@admin_bp.route('/delete_system_holiday/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_system_holiday(id):
    """Delete a system holiday - FIXED VERSION"""
    try:
        holiday = Holiday.query.get_or_404(id)

        # Ensure this is a system holiday (not company-specific)
        if holiday.company_id is not None:
            flash('This is not a system holiday and cannot be deleted here', 'danger')
            return redirect(url_for('admin.admin_holidays'))

        # FIXED: Delete all related company holiday overrides first
        CompanyHolidayOverride.query.filter_by(holiday_id=holiday.id).delete()

        # Then delete the holiday itself
        db.session.delete(holiday)
        db.session.commit()

        flash(f'System holiday "{holiday.name}" deleted successfully', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting holiday: {str(e)}', 'danger')
        print(f"Error deleting system holiday {id}: {e}")
        import traceback
        traceback.print_exc()

    return redirect(url_for('admin.admin_holidays'))


@admin_bp.route('/system_holidays')
@login_required
@admin_required
def admin_holidays():
    """Manage system-wide holidays - FIXED VERSION"""
    # Get all holiday types
    holiday_types = HolidayType.query.all()

    # Get system holidays (no company_id) grouped by type
    public_holiday_types = HolidayType.query.filter(
        HolidayType.name.contains('Public Holiday')
    ).all()

    school_holiday_types = HolidayType.query.filter(
        HolidayType.name.contains('School Holiday')
    ).all()

    public_type_ids = [ht.id for ht in public_holiday_types]
    school_type_ids = [ht.id for ht in school_holiday_types]

    public_holidays = Holiday.query.filter(
        Holiday.company_id.is_(None),  # System holidays only
        Holiday.holiday_type_id.in_(public_type_ids)
    ).order_by(Holiday.date).all()

    school_holidays = Holiday.query.filter(
        Holiday.company_id.is_(None),  # System holidays only
        Holiday.holiday_type_id.in_(school_type_ids)
    ).order_by(Holiday.date).all()

    return render_template('admin/system_holidays.html',
                           holiday_types=holiday_types,
                           public_holidays=public_holidays,
                           school_holidays=school_holidays)


@admin_bp.route('/add_holiday_type', methods=['GET', 'POST'])
@login_required
@admin_required
def add_holiday_type():
    if request.method == 'POST':
        name = request.form['name']
        color = request.form['color']

        # Check if holiday type already exists
        existing_type = HolidayType.query.filter_by(name=name).first()
        if existing_type:
            flash('Holiday type already exists', 'danger')
            return redirect(url_for('admin.add_holiday_type'))

        new_holiday_type = HolidayType(
            name=name,
            color=color,
            is_system=False
        )

        db.session.add(new_holiday_type)
        db.session.commit()

        flash('Holiday type added successfully', 'success')
        return redirect(url_for('admin.admin_holidays'))

    return render_template('admin/add_holiday_type.html')


@admin_bp.route('/edit_holiday_type/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_holiday_type(id):
    holiday_type = HolidayType.query.get_or_404(id)

    # Prevent editing system types
    if holiday_type.is_system:
        flash('System holiday types cannot be edited', 'danger')
        return redirect(url_for('admin.admin_holidays'))

    if request.method == 'POST':
        holiday_type.name = request.form['name']
        holiday_type.color = request.form['color']

        db.session.commit()
        flash('Holiday type updated successfully', 'success')
        return redirect(url_for('admin.admin_holidays'))

    return render_template('admin/edit_holiday_type.html', holiday_type=holiday_type)


@admin_bp.route('/delete_holiday_type/<int:id>')
@login_required
@admin_required
def delete_holiday_type(id):
    holiday_type = HolidayType.query.get_or_404(id)

    # Prevent deleting system types
    if holiday_type.is_system:
        flash('System holiday types cannot be deleted', 'danger')
        return redirect(url_for('admin.admin_holidays'))

    # Check if any holidays use this type
    if holiday_type.holidays:
        flash('Cannot delete holiday type that is in use', 'danger')
        return redirect(url_for('admin.admin_holidays'))

    db.session.delete(holiday_type)
    db.session.commit()

    flash('Holiday type deleted successfully', 'success')
    return redirect(url_for('admin.admin_holidays'))


@admin_bp.route('/add_holiday', methods=['GET', 'POST'])
@login_required
@admin_required
def add_holiday():
    holiday_types = HolidayType.query.all()

    if request.method == 'POST':
        name = request.form['name']
        date_str = request.form['date']
        holiday_type_id = request.form['holiday_type_id']
        is_recurring = 'is_recurring' in request.form

        # Convert date string to date object
        holiday_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        # Create new holiday
        new_holiday = Holiday(
            name=name,
            date=holiday_date,
            holiday_type_id=holiday_type_id,
            is_recurring=is_recurring
        )

        db.session.add(new_holiday)
        db.session.commit()

        flash('Holiday added successfully', 'success')
        return redirect(url_for('admin.admin_holidays'))

    return render_template('admin/add_holiday.html', holiday_types=holiday_types)


@admin_bp.route('/edit_holiday/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_holiday(id):
    holiday = Holiday.query.get_or_404(id)
    holiday_types = HolidayType.query.all()

    if request.method == 'POST':
        holiday.name = request.form['name']
        holiday.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        holiday.holiday_type_id = request.form['holiday_type_id']
        holiday.is_recurring = 'is_recurring' in request.form

        db.session.commit()
        flash('Holiday updated successfully', 'success')
        return redirect(url_for('admin.admin_holidays'))

    return render_template('admin/edit_holiday.html', holiday=holiday, holiday_types=holiday_types)


@admin_bp.route('/delete_holiday/<int:id>')
@login_required
@admin_required
def delete_holiday(id):
    holiday = Holiday.query.get_or_404(id)

    db.session.delete(holiday)
    db.session.commit()

    flash('Holiday deleted successfully', 'success')
    return redirect(url_for('admin.admin_holidays'))


@admin_bp.route('/bulk_delete_holidays', methods=['POST'])
@login_required
@admin_required
def bulk_delete_holidays():
    """Bulk delete system holidays - FIXED VERSION"""
    try:
        # Get holiday IDs from form data
        holiday_ids = request.form.getlist('holiday_ids')

        if not holiday_ids:
            flash('No holidays selected for deletion', 'warning')
            return redirect(url_for('admin.admin_holidays'))

        # Convert to integers and validate
        try:
            holiday_ids = [int(id) for id in holiday_ids]
        except ValueError:
            flash('Invalid holiday IDs provided', 'danger')
            return redirect(url_for('admin.admin_holidays'))

        # Get the holidays to be deleted
        holidays_to_delete = Holiday.query.filter(
            Holiday.id.in_(holiday_ids),
            Holiday.company_id.is_(None)  # Only allow deletion of system holidays
        ).all()

        if not holidays_to_delete:
            flash('No valid system holidays found for deletion', 'warning')
            return redirect(url_for('admin.admin_holidays'))

        deleted_count = 0

        # Delete holidays and their related overrides
        for holiday in holidays_to_delete:
            try:
                # FIXED: Delete all related company holiday overrides first
                CompanyHolidayOverride.query.filter_by(holiday_id=holiday.id).delete()

                # Then delete the holiday itself
                db.session.delete(holiday)
                deleted_count += 1

            except Exception as e:
                print(f"Error deleting holiday {holiday.id}: {e}")
                continue

        # Commit all changes
        db.session.commit()

        if deleted_count > 0:
            flash(f'Successfully deleted {deleted_count} system holiday(s)', 'success')
        else:
            flash('No holidays were deleted', 'warning')

    except Exception as e:
        db.session.rollback()
        flash(f'Error during bulk delete: {str(e)}', 'danger')
        print(f"Error in bulk delete holidays: {e}")
        import traceback
        traceback.print_exc()

    return redirect(url_for('admin.admin_holidays'))


@admin_bp.route('/data_management')
@login_required
@admin_required
def data_management():
    """Data management dashboard for CSV import/export - UPDATED VERSION"""
    # Get counts for current admin's company
    company_id = current_user.company_id

    issues_count = Issue.query.filter_by(company_id=company_id).count()
    bookings_count = BookingForm.query.filter_by(company_id=company_id).count()
    contacts_count = Contact.query.filter_by(company_id=company_id).count()
    expenses_count = ExpenseData.query.filter_by(company_id=company_id).count()
    units_count = Unit.query.filter_by(company_id=company_id).count()

    stats = {
        'issues_count': issues_count,
        'bookings_count': bookings_count,
        'contacts_count': contacts_count,
        'expenses_count': expenses_count,
        'units_count': units_count
    }

    return render_template('admin/data_management.html', stats=stats)


@admin_bp.route('/export/issues')
@login_required
@admin_required
def export_issues():
    """Export all issues for admin's company to CSV"""
    try:
        # Get all issues for the admin's company
        issues = Issue.query.filter_by(company_id=current_user.company_id).all()

        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'ID', 'Unit', 'Description', 'Category', 'Issue Item', 'Date Added',
            'Reported By', 'Priority', 'Status', 'Type', 'Solution', 'Guest Name',
            'Cost', 'Assigned To'
        ])

        # Write data rows
        for issue in issues:
            writer.writerow([
                issue.id,
                issue.unit,
                issue.description,
                issue.category.name if issue.category else '',
                issue.issue_item.name if issue.issue_item else '',
                issue.date_added.strftime('%Y-%m-%d %H:%M:%S'),
                issue.reported_by.name if issue.reported_by else '',
                issue.priority.name if issue.priority else '',
                issue.status.name if issue.status else '',
                issue.type.name if issue.type else '',
                issue.solution or '',
                issue.guest_name or '',
                float(issue.cost) if issue.cost else '',
                issue.assigned_to or ''
            ])

        # Create response
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers[
            'Content-Disposition'] = f'attachment; filename=issues_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

        return response

    except Exception as e:
        flash(f'Error exporting issues: {str(e)}', 'danger')
        return redirect(url_for('admin.data_management'))


@admin_bp.route('/export/bookings')
@login_required
@admin_required
def export_bookings():
    """Export all bookings for admin's company to CSV"""
    try:
        # Get all bookings for the admin's company
        bookings = BookingForm.query.filter_by(company_id=current_user.company_id).all()

        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'ID', 'Guest Name', 'Contact Number', 'Check In Date', 'Check Out Date',
            'Property Name', 'Unit Number', 'Number of Nights', 'Number of Guests',
            'Price', 'Booking Source', 'Payment Status', 'Notes', 'Confirmation Code',
            'Adults', 'Children', 'Infants', 'Booking Date', 'Date Added'
        ])

        # Write data rows
        for booking in bookings:
            writer.writerow([
                booking.id,
                booking.guest_name,
                booking.contact_number,
                booking.check_in_date.strftime('%Y-%m-%d'),
                booking.check_out_date.strftime('%Y-%m-%d'),
                booking.property_name or '',
                booking.unit.unit_number if booking.unit else '',
                booking.number_of_nights,
                booking.number_of_guests,
                float(booking.price) if booking.price else '',
                booking.booking_source,
                booking.payment_status,
                booking.notes or '',
                booking.confirmation_code or '',
                booking.adults or '',
                booking.children or '',
                booking.infants or '',
                booking.booking_date.strftime('%Y-%m-%d') if booking.booking_date else '',
                booking.date_added.strftime('%Y-%m-%d %H:%M:%S')
            ])

        # Create response
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers[
            'Content-Disposition'] = f'attachment; filename=bookings_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

        return response

    except Exception as e:
        flash(f'Error exporting bookings: {str(e)}', 'danger')
        return redirect(url_for('admin.data_management'))


@admin_bp.route('/import/sample_issues', methods=['POST'])
@login_required
@admin_required
def import_sample_issues():
    """Import sample issues data for admin's company with proper issue items"""
    try:
        company_id = current_user.company_id

        # Get units for this company
        units = Unit.query.filter_by(company_id=company_id).all()
        if not units:
            flash('No units found. Please create units first.', 'danger')
            return redirect(url_for('admin.data_management'))

        # Get required lookup data
        categories = {cat.name: cat.id for cat in Category.query.all()}
        reported_by = {rep.name: rep.id for rep in ReportedBy.query.all()}
        priorities = {pri.name: pri.id for pri in Priority.query.all()}
        statuses = {stat.name: stat.id for stat in Status.query.all()}
        types = {typ.name: typ.id for typ in Type.query.all()}

        # Helper function to get or create issue item
        def get_or_create_issue_item(item_name, category_id):
            if not item_name or not category_id:
                return None

            # Check if issue item exists
            issue_item = IssueItem.query.filter_by(
                name=item_name,
                category_id=category_id
            ).first()

            if not issue_item:
                # Create new issue item
                issue_item = IssueItem(name=item_name, category_id=category_id)
                db.session.add(issue_item)
                db.session.flush()

            return issue_item.id

        # Sample issues data with proper issue items
        sample_issues = [
            {
                'unit': units[0].unit_number,
                'description': 'Air conditioning not cooling properly in bedroom',
                'category': 'Aircond Issue',
                'issue_item': 'AC not cold',
                'reported_by': 'Guest',
                'priority': 'High',
                'status': 'Pending',
                'type': 'Repair',
                'solution': '',
                'guest_name': 'John Smith',
                'cost': 150.00,
                'assigned_to': 'Maintenance Team'
            },
            {
                'unit': units[0].unit_number if len(units) == 1 else units[1].unit_number,
                'description': 'Toilet bowl is clogged and not flushing',
                'category': 'Plumbing Issues',
                'issue_item': 'Toilet bowl stuck',
                'reported_by': 'Cleaner',
                'priority': 'High',
                'status': 'Pending',
                'type': 'Repair',
                'solution': '',
                'guest_name': '',
                'cost': 80.00,
                'assigned_to': 'Plumber'
            },
            {
                'unit': units[0].unit_number,
                'description': 'TV remote control not working',
                'category': 'Electrical Issue',
                'issue_item': 'Remote control',
                'reported_by': 'Guest',
                'priority': 'Low',
                'status': 'Resolved',
                'type': 'Replace',
                'solution': 'Replaced batteries and tested - working now',
                'guest_name': 'Mary Johnson',
                'cost': 5.00,
                'assigned_to': 'Staff'
            },
            {
                'unit': units[0].unit_number if len(units) == 1 else units[1].unit_number,
                'description': 'Bedsheets have stains and smell bad',
                'category': 'Cleaning Issue',
                'issue_item': 'Bedsheet - Smelly',
                'reported_by': 'Guest',
                'priority': 'Medium',
                'status': 'Resolved',
                'type': 'Replace',
                'solution': 'Replaced with fresh bedsheets',
                'guest_name': 'David Lee',
                'cost': 25.00,
                'assigned_to': 'Housekeeping'
            },
            {
                'unit': units[0].unit_number,
                'description': 'Cannot access WiFi - password not working',
                'category': 'Electrical Issue',
                'issue_item': 'Internet WiFi',
                'reported_by': 'Guest',
                'priority': 'Medium',
                'status': 'Resolved',
                'type': 'Repair',
                'solution': 'Reset router and provided new password',
                'guest_name': 'Sarah Wilson',
                'cost': 0.00,
                'assigned_to': 'IT Support'
            }
        ]

        created_count = 0

        for issue_data in sample_issues:
            # Find the unit
            unit = Unit.query.filter_by(
                unit_number=issue_data['unit'],
                company_id=company_id
            ).first()

            if not unit:
                continue

            # Get category ID
            category_id = categories.get(issue_data['category'])

            # Get or create issue item
            issue_item_id = get_or_create_issue_item(
                issue_data['issue_item'],
                category_id
            )

            # Create the issue
            new_issue = Issue(
                description=issue_data['description'],
                unit=issue_data['unit'],
                unit_id=unit.id,
                category_id=category_id,
                reported_by_id=reported_by.get(issue_data['reported_by']),
                priority_id=priorities.get(issue_data['priority']),
                status_id=statuses.get(issue_data['status']),
                type_id=types.get(issue_data['type']),
                issue_item_id=issue_item_id,  # Now properly set
                solution=issue_data['solution'],
                guest_name=issue_data['guest_name'],
                cost=issue_data['cost'],
                assigned_to=issue_data['assigned_to'],
                user_id=current_user.id,
                company_id=company_id,
                date_added=datetime.utcnow()
            )

            db.session.add(new_issue)
            created_count += 1

        db.session.commit()
        flash(f'Successfully imported {created_count} sample issues with issue items!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error importing sample issues: {str(e)}', 'danger')

    return redirect(url_for('admin.data_management'))


@admin_bp.route('/import/sample_bookings', methods=['POST'])
@login_required
@admin_required
def import_sample_bookings():
    """Import sample bookings data for admin's company"""
    try:
        company_id = current_user.company_id

        # Get units for this company
        units = Unit.query.filter_by(company_id=company_id).all()
        if not units:
            flash('No units found. Please create units first.', 'danger')
            return redirect(url_for('admin.data_management'))

        # Sample bookings data
        today = date.today()
        sample_bookings = [
            {
                'guest_name': 'Alice Thompson',
                'contact_number': '+60123456789',
                'check_in_date': today,
                'check_out_date': date(today.year, today.month, today.day + 3),
                'property_name': 'Cozy Apartment',
                'unit': units[0].unit_number,
                'adults': 2,
                'children': 1,
                'infants': 0,
                'price': 450.00,
                'booking_source': 'Airbnb',
                'payment_status': 'Paid',
                'notes': 'Early check-in requested',
                'confirmation_code': 'AIRBNB123456'
            },
            {
                'guest_name': 'Robert Chen',
                'contact_number': '+60198765432',
                'check_in_date': date(today.year, today.month, today.day + 5),
                'check_out_date': date(today.year, today.month, today.day + 8),
                'property_name': 'Modern Studio',
                'unit': units[0].unit_number if len(units) == 1 else units[1].unit_number,
                'adults': 1,
                'children': 0,
                'infants': 0,
                'price': 300.00,
                'booking_source': 'Booking.com',
                'payment_status': 'Paid',
                'notes': 'Business traveler',
                'confirmation_code': 'BDC789012'
            },
            {
                'guest_name': 'Maria Garcia',
                'contact_number': '+60187654321',
                'check_in_date': date(today.year, today.month, today.day + 10),
                'check_out_date': date(today.year, today.month, today.day + 14),
                'property_name': 'Family Suite',
                'unit': units[0].unit_number,
                'adults': 2,
                'children': 2,
                'infants': 1,
                'price': 800.00,
                'booking_source': 'WhatsApp',
                'payment_status': 'Pending',
                'notes': 'Family vacation, needs baby cot',
                'confirmation_code': 'WA345678'
            },
            {
                'guest_name': 'James Wilson',
                'contact_number': '+60176543210',
                'check_in_date': date(today.year, today.month, today.day - 2),
                'check_out_date': date(today.year, today.month, today.day + 1),
                'property_name': 'Executive Apartment',
                'unit': units[0].unit_number if len(units) == 1 else units[1].unit_number,
                'adults': 1,
                'children': 0,
                'infants': 0,
                'price': 450.00,
                'booking_source': 'Agoda',
                'payment_status': 'Paid',
                'notes': 'Extended stay guest',
                'confirmation_code': 'AGO901234'
            }
        ]

        created_count = 0

        for booking_data in sample_bookings:
            # Find the unit
            unit = Unit.query.filter_by(
                unit_number=booking_data['unit'],
                company_id=company_id
            ).first()

            if not unit:
                continue

            # Calculate nights and total guests
            nights = (booking_data['check_out_date'] - booking_data['check_in_date']).days
            total_guests = booking_data['adults'] + booking_data['children'] + booking_data['infants']

            # Create the booking
            new_booking = BookingForm(
                guest_name=booking_data['guest_name'],
                contact_number=booking_data['contact_number'],
                check_in_date=booking_data['check_in_date'],
                check_out_date=booking_data['check_out_date'],
                property_name=booking_data['property_name'],
                unit_id=unit.id,
                number_of_nights=nights,
                number_of_guests=total_guests,
                price=booking_data['price'],
                booking_source=booking_data['booking_source'],
                payment_status=booking_data['payment_status'],
                notes=booking_data['notes'],
                confirmation_code=booking_data['confirmation_code'],
                adults=booking_data['adults'],
                children=booking_data['children'],
                infants=booking_data['infants'],
                booking_date=today,
                company_id=company_id,
                user_id=current_user.id,
                date_added=datetime.utcnow()
            )

            db.session.add(new_booking)
            created_count += 1

        db.session.commit()
        flash(f'Successfully imported {created_count} sample bookings!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error importing sample bookings: {str(e)}', 'danger')

    return redirect(url_for('admin.data_management'))


# Update your existing import_csv route to handle the new data types
@admin_bp.route('/import/csv', methods=['POST'])
@login_required
@admin_required
def import_csv():
    """Import data from uploaded CSV file - UPDATED VERSION"""
    try:
        if 'csv_file' not in request.files:
            flash('No file selected', 'danger')
            return redirect(url_for('admin.data_management'))

        file = request.files['csv_file']
        data_type = request.form.get('data_type')

        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('admin.data_management'))

        if not file.filename.lower().endswith('.csv'):
            flash('Please upload a CSV file', 'danger')
            return redirect(url_for('admin.data_management'))

        # Read CSV content
        csv_content = file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(csv_content))

        if data_type == 'issues':
            return import_issues_from_csv(csv_reader)
        elif data_type == 'bookings':
            return import_bookings_from_csv(csv_reader)
        elif data_type == 'contacts':
            return import_contacts_from_csv(csv_reader)
        elif data_type == 'expenses':
            return import_expenses_from_csv(csv_reader)
        else:
            flash('Invalid data type selected', 'danger')
            return redirect(url_for('admin.data_management'))

    except Exception as e:
        flash(f'Error importing CSV: {str(e)}', 'danger')
        return redirect(url_for('admin.data_management'))


def import_issues_from_csv(csv_reader):
    """Improved helper function to import issues from CSV with better issue item handling"""
    try:
        company_id = current_user.company_id
        units = {unit.unit_number: unit.id for unit in Unit.query.filter_by(company_id=company_id).all()}
        categories = {cat.name: cat.id for cat in Category.query.all()}
        reported_by = {rep.name: rep.id for rep in ReportedBy.query.all()}
        priorities = {pri.name: pri.id for pri in Priority.query.all()}
        statuses = {stat.name: stat.id for stat in Status.query.all()}
        types = {typ.name: typ.id for typ in Type.query.all()}

        # Get existing issue items by name and category
        existing_items = {}
        for item in IssueItem.query.all():
            key = f"{item.name}_{item.category_id}" if item.category_id else item.name
            existing_items[key] = item.id

        created_count = 0

        for row in csv_reader:
            unit_number = row.get('Unit', '').strip()
            if unit_number not in units:
                print(f"Skipping row: Unit '{unit_number}' not found")
                continue

            # Get category info
            category_name = row.get('Category', '').strip()
            category_id = categories.get(category_name)

            # Handle Issue Item
            issue_item_name = row.get('Issue Item', '').strip()
            issue_item_id = None

            if issue_item_name and category_id:
                # Try to find existing issue item for this category
                item_key = f"{issue_item_name}_{category_id}"
                issue_item_id = existing_items.get(item_key)

                # If not found, try without category (fallback)
                if not issue_item_id:
                    issue_item_id = existing_items.get(issue_item_name)

                # If still not found, create new issue item
                if not issue_item_id:
                    try:
                        new_issue_item = IssueItem(
                            name=issue_item_name,
                            category_id=category_id
                        )
                        db.session.add(new_issue_item)
                        db.session.flush()  # Get the ID
                        issue_item_id = new_issue_item.id

                        # Add to our cache
                        existing_items[item_key] = issue_item_id
                        print(f"Created new issue item: {issue_item_name} for category {category_name}")

                    except Exception as e:
                        print(f"Error creating issue item '{issue_item_name}': {str(e)}")

            # Parse cost field more robustly
            cost_value = row.get('Cost', '').strip()
            cost = None
            if cost_value:
                try:
                    # Remove any non-numeric characters except decimal point
                    import re
                    cost_cleaned = re.sub(r'[^\d.]', '', str(cost_value))
                    if cost_cleaned:
                        cost = float(cost_cleaned)
                except (ValueError, TypeError):
                    cost = None

            # Parse date if provided, otherwise use current time
            date_added = datetime.utcnow()
            date_added_str = row.get('Date Added', '').strip()
            if date_added_str:
                try:
                    # Try different date formats
                    for date_format in ['%d/%m/%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y']:
                        try:
                            date_added = datetime.strptime(date_added_str, date_format)
                            break
                        except ValueError:
                            continue
                except Exception as e:
                    print(f"Could not parse date '{date_added_str}': {str(e)}")

            new_issue = Issue(
                description=row.get('Description', '').strip(),
                unit=unit_number,
                unit_id=units[unit_number],
                category_id=category_id,
                reported_by_id=reported_by.get(row.get('Reported By', '').strip()),
                priority_id=priorities.get(row.get('Priority', '').strip()),
                status_id=statuses.get(row.get('Status', '').strip()),
                type_id=types.get(row.get('Type', '').strip()),
                issue_item_id=issue_item_id,  # This should now be populated
                solution=row.get('Solution', '').strip(),
                guest_name=row.get('Guest Name', '').strip(),
                cost=cost,
                assigned_to=row.get('Assigned To', '').strip(),
                user_id=current_user.id,
                company_id=company_id,
                date_added=date_added
            )

            db.session.add(new_issue)
            created_count += 1
            print(f"Created issue: {new_issue.description[:50]}... with issue_item_id: {issue_item_id}")

        db.session.commit()
        flash(f'Successfully imported {created_count} issues from CSV!', 'success')

    except Exception as e:
        db.session.rollback()
        print(f"Full error details: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Error importing issues from CSV: {str(e)}', 'danger')

    return redirect(url_for('admin.data_management'))


def import_bookings_from_csv(csv_reader):
    """Helper function to import bookings from CSV"""
    try:
        company_id = current_user.company_id
        units = {unit.unit_number: unit.id for unit in Unit.query.filter_by(company_id=company_id).all()}

        created_count = 0

        for row in csv_reader:
            unit_number = row.get('Unit Number', '').strip()
            if unit_number not in units:
                continue

            # Parse dates
            check_in_date = datetime.strptime(row.get('Check In Date', ''), '%Y-%m-%d').date()
            check_out_date = datetime.strptime(row.get('Check Out Date', ''), '%Y-%m-%d').date()
            booking_date = None
            if row.get('Booking Date'):
                booking_date = datetime.strptime(row.get('Booking Date'), '%Y-%m-%d').date()

            nights = (check_out_date - check_in_date).days
            adults = int(row.get('Adults', 0)) if row.get('Adults') else 0
            children = int(row.get('Children', 0)) if row.get('Children') else 0
            infants = int(row.get('Infants', 0)) if row.get('Infants') else 0
            total_guests = adults + children + infants

            new_booking = BookingForm(
                guest_name=row.get('Guest Name', ''),
                contact_number=row.get('Contact Number', ''),
                check_in_date=check_in_date,
                check_out_date=check_out_date,
                property_name=row.get('Property Name', ''),
                unit_id=units[unit_number],
                number_of_nights=nights,
                number_of_guests=total_guests,
                price=float(row.get('Price', 0)) if row.get('Price') else 0,
                booking_source=row.get('Booking Source', ''),
                payment_status=row.get('Payment Status', 'Pending'),
                notes=row.get('Notes', ''),
                confirmation_code=row.get('Confirmation Code', ''),
                adults=adults,
                children=children,
                infants=infants,
                booking_date=booking_date,
                company_id=company_id,
                user_id=current_user.id,
                date_added=datetime.utcnow()
            )

            db.session.add(new_booking)
            created_count += 1

        db.session.commit()
        flash(f'Successfully imported {created_count} bookings from CSV!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error importing bookings from CSV: {str(e)}', 'danger')

    return redirect(url_for('admin.data_management'))


# ============ CONTACTS CSV IMPORT/EXPORT ============

@admin_bp.route('/export/contacts')
@login_required
@admin_required
def export_contacts():
    """Export all contacts for admin's company to CSV"""
    try:
        # Get all contacts for the admin's company
        contacts = Contact.query.filter_by(company_id=current_user.company_id).all()

        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'ID', 'Full Name', 'Role', 'Phone', 'Building', 'Favourite',
            'Notes', 'Date Added'
        ])

        # Write data rows
        for contact in contacts:
            writer.writerow([
                contact.id,
                contact.full_name,
                contact.role,
                contact.phone or '',
                contact.building or '',
                'Yes' if contact.favourite else 'No',
                contact.notes or '',
                contact.date_added.strftime('%Y-%m-%d %H:%M:%S')
            ])

        # Create response
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers[
            'Content-Disposition'] = f'attachment; filename=contacts_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

        return response

    except Exception as e:
        flash(f'Error exporting contacts: {str(e)}', 'danger')
        return redirect(url_for('admin.data_management'))


@admin_bp.route('/import/sample_contacts', methods=['POST'])
@login_required
@admin_required
def import_sample_contacts():
    """Import sample contacts data for admin's company"""
    try:
        company_id = current_user.company_id

        # Get units for building references
        units = Unit.query.filter_by(company_id=company_id).all()
        buildings = list(set([unit.building for unit in units if unit.building]))
        default_building = buildings[0] if buildings else "Main Building"

        # Sample contacts data
        sample_contacts = [
            {
                'full_name': 'Ahmad Rahman',
                'role': 'Security Guard',
                'phone': '+60123456789',
                'building': default_building,
                'favourite': True,
                'notes': '24-hour security, speaks English and Malay'
            },
            {
                'full_name': 'Siti Aminah',
                'role': 'Cleaner',
                'phone': '+60198765432',
                'building': default_building,
                'favourite': True,
                'notes': 'Daily cleaning service, very reliable'
            },
            {
                'full_name': 'Wong Mei Ling',
                'role': 'Maintenance',
                'phone': '+60187654321',
                'building': default_building,
                'favourite': False,
                'notes': 'Plumbing and electrical repairs, available weekdays'
            },
            {
                'full_name': 'Raj Kumar',
                'role': 'Property Manager',
                'phone': '+60176543210',
                'building': default_building,
                'favourite': True,
                'notes': 'Building manager, handles tenant issues'
            },
            {
                'full_name': 'Fatimah Hassan',
                'role': 'Laundry Service',
                'phone': '+60165432109',
                'building': default_building,
                'favourite': False,
                'notes': 'Pickup and delivery service, operates Monday-Saturday'
            },
            {
                'full_name': 'Dr. Lim Wei Ming',
                'role': 'Medical',
                'phone': '+60154321098',
                'building': 'Nearby Clinic',
                'favourite': True,
                'notes': 'Family clinic 5 minutes walk, emergency contact'
            },
            {
                'full_name': 'Ali Grocery Store',
                'role': 'Supplier',
                'phone': '+60143210987',
                'building': 'Ground Floor',
                'favourite': False,
                'notes': 'Daily necessities, accepts phone orders'
            },
            {
                'full_name': 'Sarah Internet Tech',
                'role': 'IT Support',
                'phone': '+60132109876',
                'building': default_building,
                'favourite': False,
                'notes': 'WiFi and internet issues, remote support available'
            }
        ]

        created_count = 0

        for contact_data in sample_contacts:
            new_contact = Contact(
                full_name=contact_data['full_name'],
                role=contact_data['role'],
                phone=contact_data['phone'],
                building=contact_data['building'],
                favourite=contact_data['favourite'],
                notes=contact_data['notes'],
                company_id=company_id,
                user_id=current_user.id,
                date_added=datetime.utcnow()
            )

            db.session.add(new_contact)
            created_count += 1

        db.session.commit()
        flash(f'Successfully imported {created_count} sample contacts!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error importing sample contacts: {str(e)}', 'danger')

    return redirect(url_for('admin.data_management'))


def import_contacts_from_csv(csv_reader):
    """Helper function to import contacts from CSV"""
    try:
        company_id = current_user.company_id
        created_count = 0

        for row in csv_reader:
            full_name = row.get('Full Name', '').strip()
            if not full_name:
                continue  # Skip rows without name

            # Parse favourite field
            favourite_value = row.get('Favourite', '').strip().lower()
            favourite = favourite_value in ['yes', 'true', '1', 'favourite', 'favorite']

            # Parse date if provided
            date_added = datetime.utcnow()
            date_added_str = row.get('Date Added', '').strip()
            if date_added_str:
                try:
                    for date_format in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y']:
                        try:
                            date_added = datetime.strptime(date_added_str, date_format)
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass  # Use default date if parsing fails

            new_contact = Contact(
                full_name=full_name,
                role=row.get('Role', '').strip(),
                phone=row.get('Phone', '').strip(),
                building=row.get('Building', '').strip(),
                favourite=favourite,
                notes=row.get('Notes', '').strip(),
                company_id=company_id,
                user_id=current_user.id,
                date_added=date_added
            )

            db.session.add(new_contact)
            created_count += 1

        db.session.commit()
        flash(f'Successfully imported {created_count} contacts from CSV!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error importing contacts from CSV: {str(e)}', 'danger')

    return redirect(url_for('admin.data_management'))


# ============ EXPENSES CSV IMPORT/EXPORT ============

@admin_bp.route('/export/expenses')
@login_required
@admin_required
def export_expenses():
    """Export all expenses for admin's company to CSV"""
    try:
        # Get all expense data for the admin's company
        expenses = ExpenseData.query.filter_by(company_id=current_user.company_id).all()

        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'ID', 'Unit Number', 'Year', 'Month', 'Sales', 'Rental', 'Electricity',
            'Water', 'Sewage', 'Internet', 'Cleaner', 'Laundry', 'Supplies',
            'Repair', 'Replace', 'Other', 'Created At', 'Updated At'
        ])

        # Write data rows
        for expense in expenses:
            writer.writerow([
                expense.id,
                expense.unit.unit_number if expense.unit else '',
                expense.year,
                expense.month,
                expense.sales or '',
                expense.rental or '',
                expense.electricity or '',
                expense.water or '',
                expense.sewage or '',
                expense.internet or '',
                expense.cleaner or '',
                expense.laundry or '',
                expense.supplies or '',
                expense.repair or '',
                expense.replace or '',
                expense.other or '',
                expense.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                expense.updated_at.strftime('%Y-%m-%d %H:%M:%S')
            ])

        # Create response
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers[
            'Content-Disposition'] = f'attachment; filename=expenses_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

        return response

    except Exception as e:
        flash(f'Error exporting expenses: {str(e)}', 'danger')
        return redirect(url_for('admin.data_management'))


@admin_bp.route('/import/sample_expenses', methods=['POST'])
@login_required
@admin_required
def import_sample_expenses():
    """Import sample expenses data for admin's company"""
    try:
        company_id = current_user.company_id

        # Get units for this company
        units = Unit.query.filter_by(company_id=company_id).all()
        if not units:
            flash('No units found. Please create units first.', 'danger')
            return redirect(url_for('admin.data_management'))

        # Get current date info
        current_date = datetime.now()
        current_year = current_date.year
        current_month = current_date.month

        # Sample expenses data for different months and units
        sample_expenses = []

        # Create data for last 3 months for each unit
        for month_offset in range(3):
            target_date = current_date - timedelta(days=30 * month_offset)
            target_year = target_date.year
            target_month = target_date.month

            for i, unit in enumerate(units[:3]):  # Limit to first 3 units
                # Vary the expenses based on unit and month
                base_multiplier = 1 + (i * 0.2)  # Different base costs per unit
                month_multiplier = 1 + (month_offset * 0.1)  # Slight variation by month

                sample_expense = {
                    'unit': unit,
                    'year': target_year,
                    'month': target_month,
                    'sales': round(2500 * base_multiplier * month_multiplier, 2),
                    'rental': round(800 * base_multiplier, 2),
                    'electricity': round(150 * base_multiplier * month_multiplier, 2),
                    'water': round(80 * base_multiplier, 2),
                    'sewage': round(30 * base_multiplier, 2),
                    'internet': round(100, 2),  # Fixed cost
                    'cleaner': round(200 * base_multiplier, 2),
                    'laundry': round(50 * base_multiplier, 2),
                    'supplies': round(120 * base_multiplier * month_multiplier, 2),
                    'repair': round(80 * month_multiplier, 2) if month_offset < 2 else 0,
                    'replace': round(150 * month_multiplier, 2) if month_offset == 0 else 0,
                    'other': round(75 * month_multiplier, 2)
                }
                sample_expenses.append(sample_expense)

        created_count = 0

        for expense_data in sample_expenses:
            # Check if expense record already exists
            existing = ExpenseData.query.filter_by(
                company_id=company_id,
                unit_id=expense_data['unit'].id,
                year=expense_data['year'],
                month=expense_data['month']
            ).first()

            if existing:
                continue  # Skip if already exists

            new_expense = ExpenseData(
                company_id=company_id,
                unit_id=expense_data['unit'].id,
                year=expense_data['year'],
                month=expense_data['month'],
                sales=str(expense_data['sales']),
                rental=str(expense_data['rental']),
                electricity=str(expense_data['electricity']),
                water=str(expense_data['water']),
                sewage=str(expense_data['sewage']),
                internet=str(expense_data['internet']),
                cleaner=str(expense_data['cleaner']),
                laundry=str(expense_data['laundry']),
                supplies=str(expense_data['supplies']),
                repair=str(expense_data['repair']),
                replace=str(expense_data['replace']),
                other=str(expense_data['other']),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            db.session.add(new_expense)
            created_count += 1

        db.session.commit()
        flash(f'Successfully imported {created_count} sample expense records!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error importing sample expenses: {str(e)}', 'danger')

    return redirect(url_for('admin.data_management'))


def import_expenses_from_csv(csv_reader):
    """Helper function to import expenses from CSV"""
    try:
        company_id = current_user.company_id
        units = {unit.unit_number: unit.id for unit in Unit.query.filter_by(company_id=company_id).all()}

        created_count = 0
        updated_count = 0

        for row in csv_reader:
            unit_number = row.get('Unit Number', '').strip()
            if unit_number not in units:
                continue

            # Parse year and month
            try:
                year = int(row.get('Year', 0))
                month = int(row.get('Month', 0))
                if year < 2000 or year > 2030 or month < 1 or month > 12:
                    continue
            except (ValueError, TypeError):
                continue

            # Check if record exists
            existing = ExpenseData.query.filter_by(
                company_id=company_id,
                unit_id=units[unit_number],
                year=year,
                month=month
            ).first()

            expense_fields = {
                'sales': row.get('Sales', '').strip(),
                'rental': row.get('Rental', '').strip(),
                'electricity': row.get('Electricity', '').strip(),
                'water': row.get('Water', '').strip(),
                'sewage': row.get('Sewage', '').strip(),
                'internet': row.get('Internet', '').strip(),
                'cleaner': row.get('Cleaner', '').strip(),
                'laundry': row.get('Laundry', '').strip(),
                'supplies': row.get('Supplies', '').strip(),
                'repair': row.get('Repair', '').strip(),
                'replace': row.get('Replace', '').strip(),
                'other': row.get('Other', '').strip()
            }

            if existing:
                # Update existing record
                for field, value in expense_fields.items():
                    if value:  # Only update if value is provided
                        setattr(existing, field, value)
                existing.updated_at = datetime.utcnow()
                updated_count += 1
            else:
                # Create new record
                new_expense = ExpenseData(
                    company_id=company_id,
                    unit_id=units[unit_number],
                    year=year,
                    month=month,
                    **expense_fields,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.session.add(new_expense)
                created_count += 1

        db.session.commit()
        flash(f'Successfully imported expenses: {created_count} created, {updated_count} updated!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error importing expenses from CSV: {str(e)}', 'danger')

    return redirect(url_for('admin.data_management'))