from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from functools import wraps
from models import db, Replacement, Unit

replacements_bp = Blueprint('replacements', __name__)

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

def replacements_view_required(f):
    return permission_required('can_view_replacements')(f)

def replacements_manage_required(f):
    return permission_required('can_manage_replacements')(f)

@replacements_bp.route('/add_replacement', methods=['POST'])
@login_required
@permission_required('can_manage_replacements')
def add_replacement():
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
        flash('You do not have permission to add replacements for this unit', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    new_replacement = Replacement(
        item=item,
        remark=remark,
        unit=unit.unit_number,  # Keep the unit number for backward compatibility
        unit_id=unit_id,  # Store the reference to the unit model
        status=status,
        author=current_user,
        company_id=current_user.company_id
    )
    db.session.add(new_replacement)
    db.session.commit()

    flash('Replacement request added successfully', 'success')
    return redirect(url_for('dashboard.dashboard'))

@replacements_bp.route('/update_replacement/<int:id>', methods=['POST'])
@login_required
@permission_required('can_manage_replacements')
def update_replacement(id):
    replacement = Replacement.query.get_or_404(id)

    # Ensure the current user's company matches the replacement's company
    if replacement.company_id != current_user.company_id:
        flash('You are not authorized to update this replacement request', 'danger')
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

        replacement.unit = unit.unit_number
        replacement.unit_id = unit_id

    replacement.item = request.form['item']
    replacement.remark = request.form['remark']
    replacement.status = request.form['status']

    db.session.commit()
    flash('Replacement request updated successfully', 'success')
    return redirect(url_for('dashboard.dashboard'))

@replacements_bp.route('/delete_replacement/<int:id>')
@login_required
@permission_required('can_manage_replacements')
def delete_replacement(id):
    replacement = Replacement.query.get_or_404(id)

    # Ensure the current user's company matches the replacement's company
    if replacement.company_id != current_user.company_id:
        flash('You are not authorized to delete this replacement request', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    db.session.delete(replacement)
    db.session.commit()

    flash('Replacement request deleted successfully', 'success')
    return redirect(url_for('dashboard.dashboard'))