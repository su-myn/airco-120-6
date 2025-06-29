from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from functools import wraps
from models import db, Issue, Unit, Category, ReportedBy, Priority, Status, Type, IssueItem
from utils.access_control import (
    filter_query_by_accessible_units,
    get_accessible_units_query,
    get_accessible_bookings_query,
    get_accessible_issues_query,
    check_unit_access,
    require_unit_access
)


issues_bp = Blueprint('issues', __name__)

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

def issues_view_required(f):
    return permission_required('can_view_issues')(f)

def issues_manage_required(f):
    return permission_required('can_manage_issues')(f)

@issues_bp.route('/issues')
@login_required
@issues_view_required
def issues():
    # Filter records to only show those for accessible units
    issues = []

    if current_user.has_permission('can_view_issues'):
        issues = get_accessible_issues_query().all()

    # Get accessible units for this user for the form
    units = get_accessible_units_query().all()

    # Get categories, priorities, statuses, etc.
    categories = Category.query.all()
    reported_by_options = ReportedBy.query.all()
    priorities = Priority.query.all()
    statuses = Status.query.all()
    types = Type.query.all()

    # Get issue items with their categories
    issue_items_by_category = {}
    for category in categories:
        issue_items_by_category[category.id] = IssueItem.query.filter_by(category_id=category.id).all()

    # Add current date/time for template calculations
    now = datetime.now()

    return render_template('issues.html',
                           issues=issues,
                           units=units,
                           categories=categories,
                           reported_by_options=reported_by_options,
                           priorities=priorities,
                           statuses=statuses,
                           types=types,
                           issue_items_by_category=issue_items_by_category,
                           now=now,
                           timedelta=timedelta)


# Replace the existing add_issue() function with this updated version:
@issues_bp.route('/add_issue', methods=['POST'])
@login_required
@permission_required('can_manage_issues')
def add_issue():
    description = request.form['description']
    unit_id = request.form['unit_id']

    # Check if user can access this unit
    if not check_unit_access(unit_id):
        flash('You do not have permission to add issues for this unit', 'danger')
        return redirect(url_for('issues.issues'))

    # New fields
    category_id = request.form.get('category_id') or None
    reported_by_id = request.form.get('reported_by_id') or None
    priority_id = request.form.get('priority_id') or None
    status_id = request.form.get('status_id') or None
    type_id = request.form.get('type_id') or None
    issue_item_id = request.form.get('issue_item_id') or None

    # Handle custom issue item
    custom_issue = request.form.get('custom_issue', '').strip()
    if custom_issue and category_id:
        # Check if this custom issue already exists
        existing_item = IssueItem.query.filter_by(name=custom_issue, category_id=category_id).first()
        if existing_item:
            issue_item_id = existing_item.id
        else:
            # Create a new issue item
            new_issue_item = IssueItem(name=custom_issue, category_id=category_id)
            db.session.add(new_issue_item)
            db.session.flush()  # Get the ID before committing
            issue_item_id = new_issue_item.id

    solution = request.form.get('solution', '')
    guest_name = request.form.get('guest_name', '')

    # Fix for cost field - convert empty string to None
    cost_value = request.form.get('cost', '')
    cost = float(cost_value) if cost_value.strip() else None

    assigned_to = request.form.get('assigned_to', '')

    # Get the unit number from the selected unit
    unit = Unit.query.get(unit_id)
    if not unit:
        flash('Invalid unit selected', 'danger')
        return redirect(url_for('issues.issues'))

    # Double-check unit access and company
    if not check_unit_access(unit_id):
        flash('You do not have permission to add issues for this unit', 'danger')
        return redirect(url_for('issues.issues'))

    new_issue = Issue(
        description=description,
        unit=unit.unit_number,
        unit_id=unit_id,
        category_id=category_id,
        reported_by_id=reported_by_id,
        priority_id=priority_id,
        status_id=status_id,
        type_id=type_id,
        issue_item_id=issue_item_id,
        solution=solution,
        guest_name=guest_name,
        cost=cost,
        assigned_to=assigned_to,
        author=current_user,
        company_id=current_user.company_id
    )
    db.session.add(new_issue)
    db.session.commit()

    flash('Issue added successfully', 'success')
    # Add the new_issue_id parameter to the redirect URL
    return redirect(url_for('issues.issues', new_issue_id=new_issue.id))


# Replace the existing update_issue() function with this updated version:
@issues_bp.route('/update_issue/<int:id>', methods=['POST'])
@login_required
@permission_required('can_manage_issues')
def update_issue(id):
    # Get the current page from the request args
    page = request.args.get('page', 1, type=int)
    issue = Issue.query.get_or_404(id)

    # Ensure the current user's company matches the issue's company
    if issue.company_id != current_user.company_id:
        flash('You are not authorized to update this issue', 'danger')
        return redirect(url_for('issues.issues'))

    # Check if user can access the current unit
    if not check_unit_access(issue.unit_id):
        flash('You do not have permission to access this issue', 'danger')
        return redirect(url_for('issues.issues'))

    unit_id = request.form.get('unit_id')

    # Get the unit if unit_id is provided and check access
    if unit_id:
        if not check_unit_access(unit_id):
            flash('You do not have permission to assign this issue to the selected unit', 'danger')
            return redirect(url_for('issues.issues'))

        unit = Unit.query.get(unit_id)
        if not unit:
            flash('Invalid unit selected', 'danger')
            return redirect(url_for('issues.issues'))

        issue.unit = unit.unit_number
        issue.unit_id = unit_id

    # Update fields
    issue.description = request.form['description']

    # Handle optional fields
    issue.category_id = request.form.get('category_id') or None
    issue.reported_by_id = request.form.get('reported_by_id') or None
    issue.priority_id = request.form.get('priority_id') or None
    issue.status_id = request.form.get('status_id') or None
    issue.type_id = request.form.get('type_id') or None

    # Handle issue item
    issue_item_id = request.form.get('issue_item_id') or None
    custom_issue = request.form.get('custom_issue', '').strip()

    if custom_issue and issue.category_id:
        # Check if this custom issue already exists
        existing_item = IssueItem.query.filter_by(name=custom_issue, category_id=issue.category_id).first()
        if existing_item:
            issue_item_id = existing_item.id
        else:
            # Create a new issue item
            new_issue_item = IssueItem(name=custom_issue, category_id=issue.category_id)
            db.session.add(new_issue_item)
            db.session.flush()  # Get the ID before committing
            issue_item_id = new_issue_item.id

    issue.issue_item_id = issue_item_id
    issue.solution = request.form.get('solution', '')
    issue.guest_name = request.form.get('guest_name', '')

    # Fix for cost field
    cost_value = request.form.get('cost', '')
    issue.cost = float(cost_value) if cost_value.strip() else None

    issue.assigned_to = request.form.get('assigned_to', '')

    db.session.commit()
    flash('Issue updated successfully', 'success')
    return redirect(url_for('issues.issues', updated_issue_id=issue.id, page=page))


# Replace the existing delete_issue() function with this updated version:
@issues_bp.route('/delete_issue/<int:id>')
@login_required
@permission_required('can_manage_issues')
def delete_issue(id):
    issue = Issue.query.get_or_404(id)

    # Ensure the current user's company matches the issue's company
    if issue.company_id != current_user.company_id:
        flash('You are not authorized to delete this issue', 'danger')
        return redirect(url_for('issues.issues'))

    # Check if user can access this unit
    if not check_unit_access(issue.unit_id):
        flash('You do not have permission to access this issue', 'danger')
        return redirect(url_for('issues.issues'))

    db.session.delete(issue)
    db.session.commit()

    flash('Issue deleted successfully', 'success')
    return redirect(url_for('issues.issues'))


# Replace the existing get_issue() function with this updated version:
@issues_bp.route('/api/issue/<int:id>')
@login_required
@permission_required('can_view_issues')
def get_issue(id):
    issue = Issue.query.get_or_404(id)

    # Ensure the current user's company matches the issue's company
    if issue.company_id != current_user.company_id:
        return jsonify({'error': 'Not authorized'}), 403

    # Check if user can access this unit
    if not check_unit_access(issue.unit_id):
        return jsonify({'error': 'Access denied to this unit'}), 403

    return jsonify({
        'id': issue.id,
        'description': issue.description,
        'unit_id': issue.unit_id,
        'category_id': issue.category_id,
        'reported_by_id': issue.reported_by_id,
        'priority_id': issue.priority_id,
        'status_id': issue.status_id,
        'type_id': issue.type_id,
        'issue_item_id': issue.issue_item_id,
        'solution': issue.solution,
        'guest_name': issue.guest_name,
        'cost': float(issue.cost) if issue.cost else 0,
        'assigned_to': issue.assigned_to
    })


# The get_issue_items() function remains the same as it doesn't need unit filtering
@issues_bp.route('/api/get_issue_items/<int:category_id>')
@login_required
def get_issue_items(category_id):
    issue_items = IssueItem.query.filter_by(category_id=category_id).all()
    items_list = [{'id': item.id, 'name': item.name} for item in issue_items]
    return jsonify(items_list)
