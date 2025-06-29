"""
Access control utilities for filtering data based on user permissions
"""

from flask_login import current_user
from models import Unit, BookingForm, Issue, ExpenseData, Complaint, Repair, Replacement
from sqlalchemy import and_


def filter_query_by_accessible_units(query, model_class):
    """
    Filter a SQLAlchemy query to only include records for units the current user can access

    Args:
        query: SQLAlchemy query object
        model_class: The model class being queried (must have unit_id attribute)

    Returns:
        Filtered query object
    """
    if not current_user.is_authenticated:
        # Return empty query if not authenticated
        return query.filter(model_class.id == -1)

    # Get accessible unit IDs for the current user
    accessible_unit_ids = current_user.get_accessible_unit_ids()

    if not accessible_unit_ids:
        # If no accessible units, return empty query
        return query.filter(model_class.id == -1)

    # Filter by accessible units and company
    if hasattr(model_class, 'unit_id'):
        return query.filter(
            and_(
                model_class.company_id == current_user.company_id,
                model_class.unit_id.in_(accessible_unit_ids)
            )
        )
    else:
        # Fallback to company filter only
        return query.filter(model_class.company_id == current_user.company_id)


def get_accessible_units_query():
    """
    Get a query for units accessible to the current user

    Returns:
        SQLAlchemy query for accessible units
    """
    if not current_user.is_authenticated:
        return Unit.query.filter(Unit.id == -1)

    accessible_unit_ids = current_user.get_accessible_unit_ids()

    if not accessible_unit_ids:
        return Unit.query.filter(Unit.id == -1)

    return Unit.query.filter(
        and_(
            Unit.company_id == current_user.company_id,
            Unit.id.in_(accessible_unit_ids)
        )
    )


def get_accessible_bookings_query():
    """Get bookings query filtered by accessible units"""
    base_query = BookingForm.query.filter_by(company_id=current_user.company_id)
    return filter_query_by_accessible_units(base_query, BookingForm)


def get_accessible_issues_query():
    """Get issues query filtered by accessible units"""
    base_query = Issue.query.filter_by(company_id=current_user.company_id)
    return filter_query_by_accessible_units(base_query, Issue)


def get_accessible_expenses_query():
    """Get expenses query filtered by accessible units"""
    base_query = ExpenseData.query.filter_by(company_id=current_user.company_id)
    return filter_query_by_accessible_units(base_query, ExpenseData)


def check_unit_access(unit_id):
    """
    Check if current user can access a specific unit

    Args:
        unit_id: ID of the unit to check

    Returns:
        Boolean indicating access permission
    """
    if not current_user.is_authenticated:
        return False

    return current_user.can_access_unit(unit_id)


def require_unit_access(unit_id):
    """
    Decorator/function to require unit access for a specific unit
    Raises an exception if access is denied

    Args:
        unit_id: ID of the unit to check

    Raises:
        PermissionError: If user doesn't have access to the unit
    """
    if not check_unit_access(unit_id):
        raise PermissionError(f"User does not have access to unit {unit_id}")