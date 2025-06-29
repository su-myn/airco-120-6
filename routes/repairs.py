from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from functools import wraps
from models import db, Repair, Unit

repairs_bp = Blueprint('repairs', __name__)

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

def repairs_view_required(f):
    return permission_required('can_view_repairs')(f)

def repairs_manage_required(f):
    return permission_required('can_manage_repairs')(f)

@repairs_bp.route('/add_repair', methods=['POST'])
@login_required
@permission_required('can_manage_repairs')
def add_repair():
    item = request.form['item']
    remark = request.form['remark']
    unit_id = request.form['unit_id']
    status = request.form['status']

    # Get the unit
    unit = Unit.query.get(unit_id)
    if not unit:
        flash('Invalid unit selected', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    # Check if the unit belongs to the user's company
    if unit.company_id != current_user.company_id:
        flash('You do not have permission to add repairs for this unit', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    new_repair = Repair(
        item=item,
        remark=remark,
        unit=unit.unit_number,  # Keep the unit number for backward compatibility
        unit_id=unit_id,  # Store the reference to the unit model
        status=status,
        author=current_user,
        company_id=current_user.company_id
    )
    db.session.add(new_repair)
    db.session.commit()

    flash('Repair request added successfully', 'success')
    return redirect(url_for('dashboard.dashboard'))

@repairs_bp.route('/update_repair/<int:id>', methods=['POST'])
@login_required
@permission_required('can_manage_repairs')
def update_repair(id):
    repair = Repair.query.get_or_404(id)

    # Ensure the current user's company matches the repair's company
    if repair.company_id != current_user.company_id:
        flash('You are not authorized to update this repair request', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    unit_id = request.form.get('unit_id')

    # Get the unit if unit_id is provided
    if unit_id:
        unit = Unit.query.get(unit_id)
        if not unit:
            flash('Invalid unit selected', 'danger')
            return redirect(url_for('dashboard.dashboard'))

        # Check if the unit belongs to the user's company
        if unit.company_id != current_user.company_id:
            flash('You do not have permission to use this unit', 'danger')
            return redirect(url_for('dashboard.dashboard'))

        repair.unit = unit.unit_number
        repair.unit_id = unit_id

    repair.item = request.form['item']
    repair.remark = request.form['remark']
    repair.status = request.form['status']

    db.session.commit()
    flash('Repair request updated successfully', 'success')
    return redirect(url_for('dashboard.dashboard'))

@repairs_bp.route('/delete_repair/<int:id>')
@login_required
@permission_required('can_manage_repairs')
def delete_repair(id):
    repair = Repair.query.get_or_404(id)

    # Ensure the current user's company matches the repair's company
    if repair.company_id != current_user.company_id:
        flash('You are not authorized to delete this repair request', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    db.session.delete(repair)
    db.session.commit()

    flash('Repair request deleted successfully', 'success')
    return redirect(url_for('dashboard.dashboard'))