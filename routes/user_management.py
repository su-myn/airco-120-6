from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from functools import wraps
from models import db, User, Company, Role, Unit, CustomUserPermission
from app import bcrypt

user_management_bp = Blueprint('user_management', __name__)


def manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('You need to be logged in to access this page.', 'danger')
            return redirect(url_for('auth.login'))

        if current_user.role.name not in ['Manager', 'Admin'] and not current_user.is_admin:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('dashboard.dashboard'))
        return f(*args, **kwargs)

    return decorated_function


@user_management_bp.route('/manage_users')
@login_required
@manager_required
def manage_users():
    """Manager interface to manage users in their company"""
    company = current_user.company

    # Get all users in the company
    users = User.query.filter_by(company_id=company.id).all()

    # Get available roles (excluding Admin role for managers)
    if current_user.is_admin:
        roles = Role.query.all()
    else:
        roles = Role.query.filter(Role.name.in_(['Manager', 'Staff', 'Cleaner'])).all()

    # Calculate current counts and limits
    user_stats = {
        'Manager': {
            'current': company.get_user_count_by_role('Manager'),
            'max': company.max_manager_users,
            'can_add': company.can_add_user_for_role('Manager')
        },
        'Staff': {
            'current': company.get_user_count_by_role('Staff'),
            'max': company.max_staff_users,
            'can_add': company.can_add_user_for_role('Staff')
        },
        'Cleaner': {
            'current': company.get_user_count_by_role('Cleaner'),
            'max': company.max_cleaner_users,
            'can_add': company.can_add_user_for_role('Cleaner')
        }
    }

    return render_template('user_management/manage_users.html',
                           users=users,
                           roles=roles,
                           user_stats=user_stats,
                           company=company)


@user_management_bp.route('/add_user', methods=['GET', 'POST'])
@login_required
@manager_required
def add_user():
    """Add a new user to the manager's company"""
    company = current_user.company

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role_id = request.form['role_id']
        is_cleaner = 'is_cleaner' in request.form

        # Get the role to check limits
        role = Role.query.get_or_404(role_id)

        # Prevent managers from creating admin users
        if not current_user.is_admin and role.is_admin:
            flash('You cannot create admin users.', 'danger')
            return redirect(url_for('user_management.add_user'))

        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('A user with this email already exists.', 'danger')
            return redirect(url_for('user_management.add_user'))

        # Check role limits
        if not company.can_add_user_for_role(role.name):
            current_count = company.get_user_count_by_role(role.name)
            max_count = company.get_max_users_for_role(role.name)
            flash(f'Cannot add more {role.name} users. Current: {current_count}/{max_count}', 'danger')
            return redirect(url_for('user_management.add_user'))

        # Create new user
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(
            name=name,
            email=email,
            password=hashed_password,
            company_id=company.id,
            role_id=role_id,
            is_cleaner=is_cleaner
        )

        try:
            db.session.add(new_user)
            db.session.commit()
            flash(f'User {name} added successfully!', 'success')
            return redirect(url_for('user_management.manage_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding user: {str(e)}', 'danger')

    # Get available roles for the form
    if current_user.is_admin:
        roles = Role.query.all()
    else:
        roles = Role.query.filter(Role.name.in_(['Manager', 'Staff', 'Cleaner'])).all()

    return render_template('user_management/add_user.html', roles=roles, company=company)


@user_management_bp.route('/edit_user/<int:id>', methods=['GET', 'POST'])
@login_required
@manager_required
def edit_user(id):
    """Edit a user in the manager's company"""
    user = User.query.get_or_404(id)

    # Ensure user belongs to the same company
    if user.company_id != current_user.company_id:
        flash('You can only edit users in your company.', 'danger')
        return redirect(url_for('user_management.manage_users'))

    # Prevent managers from editing admin users
    if not current_user.is_admin and user.role.is_admin:
        flash('You cannot edit admin users.', 'danger')
        return redirect(url_for('user_management.manage_users'))

    if request.method == 'POST':
        original_role = user.role

        user.name = request.form['name']
        user.email = request.form['email']
        new_role_id = request.form['role_id']
        user.is_cleaner = 'is_cleaner' in request.form

        # Only update password if provided
        if request.form['password'].strip():
            user.password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')

        # Check if role is changing
        if str(user.role_id) != new_role_id:
            new_role = Role.query.get_or_404(new_role_id)

            # Prevent managers from assigning admin roles
            if not current_user.is_admin and new_role.is_admin:
                flash('You cannot assign admin roles.', 'danger')
                return render_template('user_management/edit_user.html', user=user, roles=get_available_roles())

            # Check if the new role has space
            if not current_user.company.can_add_user_for_role(new_role.name):
                current_count = current_user.company.get_user_count_by_role(new_role.name)
                max_count = current_user.company.get_max_users_for_role(new_role.name)
                flash(f'Cannot change to {new_role.name} role. Current: {current_count}/{max_count}', 'danger')
                return render_template('user_management/edit_user.html', user=user, roles=get_available_roles())

            user.role_id = new_role_id

        try:
            db.session.commit()
            flash('User updated successfully!', 'success')
            return redirect(url_for('user_management.manage_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating user: {str(e)}', 'danger')

    return render_template('user_management/edit_user.html', user=user, roles=get_available_roles())


@user_management_bp.route('/delete_user/<int:id>', methods=['POST'])
@login_required
@manager_required
def delete_user(id):
    """Delete a user from the manager's company"""
    user = User.query.get_or_404(id)

    # Ensure user belongs to the same company
    if user.company_id != current_user.company_id:
        flash('You can only delete users in your company.', 'danger')
        return redirect(url_for('user_management.manage_users'))

    # Prevent self-deletion
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('user_management.manage_users'))

    # Prevent managers from deleting admin users
    if not current_user.is_admin and user.role.is_admin:
        flash('You cannot delete admin users.', 'danger')
        return redirect(url_for('user_management.manage_users'))

    try:
        # Delete custom permissions first (to avoid foreign key constraint issues)
        CustomUserPermission.query.filter_by(user_id=user.id).delete()

        # Remove user from cleaner assignments if applicable
        if user.is_cleaner:
            user.assigned_units = []

        # Delete the user
        db.session.delete(user)
        db.session.commit()

        flash(f'User {user.name} deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'danger')

    return redirect(url_for('user_management.manage_users'))


def get_available_roles():
    """Get roles available to the current user"""
    if current_user.is_admin:
        return Role.query.all()
    else:
        return Role.query.filter(Role.name.in_(['Manager', 'Staff', 'Cleaner'])).all()


@user_management_bp.route('/manage_staff_permissions/<int:user_id>', methods=['GET', 'POST'])
@login_required
@manager_required
def manage_staff_permissions(user_id):
    """Manager interface to customize permissions for a specific staff member"""
    staff_user = User.query.get_or_404(user_id)

    # Ensure staff belongs to the same company
    if staff_user.company_id != current_user.company_id:
        flash('You can only manage staff in your company.', 'danger')
        return redirect(url_for('user_management.manage_users'))

    # Only allow managing Staff and Cleaner permissions, not Managers or Admins
    if staff_user.role.name not in ['Staff', 'Cleaner']:
        flash('You can only customize permissions for Staff and Cleaner roles.', 'danger')
        return redirect(url_for('user_management.manage_users'))

    # Get or create custom permissions record
    custom_perms = CustomUserPermission.query.filter_by(
        user_id=user_id,
        company_id=current_user.company_id
    ).first()

    if not custom_perms:
        custom_perms = CustomUserPermission(
            user_id=user_id,
            company_id=current_user.company_id
        )
        db.session.add(custom_perms)
        db.session.flush()

    # Define permissions and permission groups based on role
    if staff_user.role.name == 'Cleaner':
        # Cleaners only get Issues and Analytics permissions
        permission_groups = {
            'Issues': [
                ('can_view_issues', 'View Issues'),
                ('can_manage_issues', 'Manage Issues')
            ],
            'Analytics': [
                ('can_view_analytics', 'View Analytics'),
                ('can_manage_analytics', 'Manage Analytics')
            ]
        }

        # Define available permissions for Cleaners
        permissions = [
            'can_view_issues', 'can_manage_issues',
            'can_view_analytics', 'can_manage_analytics'
        ]
    else:
        # Staff and other roles get full permission groups
        permission_groups = {
            'Bookings': [
                ('can_view_bookings', 'View Bookings'),
                ('can_manage_bookings', 'Manage Bookings')
            ],
            'Calendar': [
                ('can_view_calendar', 'View Calendar'),
                ('can_manage_calendar', 'Manage Calendar')
            ],
            'Occupancy': [
                ('can_view_occupancy', 'View Occupancy'),
                ('can_manage_occupancy', 'Manage Occupancy')
            ],
            'Issues': [
                ('can_view_issues', 'View Issues'),
                ('can_manage_issues', 'Manage Issues')
            ],
            'Analytics': [
                ('can_view_analytics', 'View Analytics'),
                ('can_manage_analytics', 'Manage Analytics')
            ],
            'Expenses': [
                ('can_view_expenses', 'View Expenses'),
                ('can_manage_expenses', 'Manage Expenses')
            ],
            'Contacts': [
                ('can_view_contacts', 'View Contacts'),
                ('can_manage_contacts', 'Manage Contacts')
            ],
            'Units': [
                ('can_view_units', 'View Units'),
                ('can_manage_units', 'Manage Units')
            ],
            'Cleaner Management': [
                ('can_view_manage_cleaners', 'View Manage Cleaners'),
                ('can_manage_manage_cleaners', 'Manage Manage Cleaners')
            ],
            'Cleaning Schedule': [
                ('can_view_jadual_pembersihan', 'View Cleaning Schedule'),
                ('can_manage_jadual_pembersihan', 'Manage Cleaning Schedule')
            ]
        }

        # Define all available permissions for Staff
        permissions = [
            'can_view_bookings', 'can_manage_bookings',
            'can_view_calendar', 'can_manage_calendar',
            'can_view_occupancy', 'can_manage_occupancy',
            'can_view_issues', 'can_manage_issues',
            'can_view_analytics', 'can_manage_analytics',
            'can_view_expenses', 'can_manage_expenses',
            'can_view_contacts', 'can_manage_contacts',
            'can_view_units', 'can_manage_units',
            'can_view_manage_cleaners', 'can_manage_manage_cleaners',
            'can_view_jadual_pembersihan', 'can_manage_jadual_pembersihan'
        ]

    if request.method == 'POST':
        # Update custom permissions based on form data
        for permission in permissions:
            form_value = request.form.get(permission)
            if form_value == 'true':
                setattr(custom_perms, permission, True)
            elif form_value == 'false':
                setattr(custom_perms, permission, False)
            else:
                # Default to False if no value provided
                setattr(custom_perms, permission, False)

        try:
            db.session.commit()
            flash(f'Permissions updated successfully for {staff_user.name}!', 'success')
            return redirect(url_for('user_management.manage_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating permissions: {str(e)}', 'danger')

    return render_template('user_management/manage_staff_permissions.html',
                           staff_user=staff_user,
                           custom_perms=custom_perms,
                           permission_groups=permission_groups)


@user_management_bp.route('/reset_staff_permissions/<int:user_id>', methods=['POST'])
@login_required
@manager_required
def reset_staff_permissions(user_id):
    """Reset staff permissions to all denied"""
    staff_user = User.query.get_or_404(user_id)

    # Ensure staff belongs to the same company
    if staff_user.company_id != current_user.company_id:
        flash('You can only manage staff in your company.', 'danger')
        return redirect(url_for('user_management.manage_users'))

    # Only allow managing Staff and Cleaner permissions
    if staff_user.role.name not in ['Staff', 'Cleaner']:
        flash('You can only reset permissions for Staff and Cleaner roles.', 'danger')
        return redirect(url_for('user_management.manage_users'))

    # Get or create custom permissions record
    custom_perms = CustomUserPermission.query.filter_by(
        user_id=user_id,
        company_id=current_user.company_id
    ).first()

    if not custom_perms:
        custom_perms = CustomUserPermission(
            user_id=user_id,
            company_id=current_user.company_id
        )
        db.session.add(custom_perms)

    # Set all permissions to False (denied)
    permissions = [
        'can_view_bookings', 'can_manage_bookings',
        'can_view_calendar', 'can_manage_calendar',
        'can_view_occupancy', 'can_manage_occupancy',
        'can_view_issues', 'can_manage_issues',
        'can_view_analytics', 'can_manage_analytics',
        'can_view_expenses', 'can_manage_expenses',
        'can_view_contacts', 'can_manage_contacts',
        'can_view_units', 'can_manage_units',
        'can_view_manage_cleaners', 'can_manage_manage_cleaners',
        'can_view_jadual_pembersihan', 'can_manage_jadual_pembersihan'
    ]

    for permission in permissions:
        setattr(custom_perms, permission, False)

    db.session.commit()
    flash(f'All permissions reset to denied for {staff_user.name}!', 'success')

    return redirect(url_for('user_management.manage_users'))


@user_management_bp.route('/manage_staff_units/<int:user_id>', methods=['GET', 'POST'])
@login_required
@manager_required
def manage_staff_units(user_id):
    """Manager interface to assign units to a specific staff member"""
    staff_user = User.query.get_or_404(user_id)

    # Ensure staff belongs to the same company
    if staff_user.company_id != current_user.company_id:
        flash('You can only manage staff in your company.', 'danger')
        return redirect(url_for('user_management.manage_users'))

    # Only allow managing Staff unit assignments
    if staff_user.role.name != 'Staff':
        flash('You can only assign units to Staff members.', 'danger')
        return redirect(url_for('user_management.manage_users'))

    # Get all units in the company
    company_units = Unit.query.filter_by(company_id=current_user.company_id).all()

    if request.method == 'POST':
        # Clear current assignments
        staff_user.assigned_staff_units = []

        # Add new assignments
        selected_units = request.form.getlist('assigned_units')
        for unit_id in selected_units:
            unit = Unit.query.get(unit_id)
            if unit and unit.company_id == current_user.company_id:
                staff_user.assigned_staff_units.append(unit)

        try:
            db.session.commit()
            flash(f'Unit assignments updated successfully for {staff_user.name}!', 'success')
            return redirect(url_for('user_management.manage_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating unit assignments: {str(e)}', 'danger')

    return render_template('user_management/manage_staff_units.html',
                           staff_user=staff_user,
                           units=company_units)


@user_management_bp.route('/api/staff_units/<int:user_id>')
@login_required
@manager_required
def get_staff_units(user_id):
    """API endpoint to get units assigned to a staff member"""
    staff_user = User.query.get_or_404(user_id)

    # Ensure staff belongs to the same company
    if staff_user.company_id != current_user.company_id:
        return jsonify({'error': 'Unauthorized'}), 403

    assigned_unit_ids = [unit.id for unit in staff_user.assigned_staff_units]
    return jsonify({'assigned_units': assigned_unit_ids})