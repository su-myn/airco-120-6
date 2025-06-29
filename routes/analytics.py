from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import pytz
from sqlalchemy import func
from models import db, Issue, Unit, Category, Priority, Status, Type, ReportedBy
from utils.access_control import (
    get_accessible_units_query,
    get_accessible_issues_query
)
import pytz

analytics_bp = Blueprint('analytics', __name__)



def convert_utc_to_malaysia_time(utc_dt):
    """Convert UTC datetime to Malaysia timezone"""
    if utc_dt is None:
        return None
    malaysia_tz = pytz.timezone('Asia/Kuala_Lumpur')
    if utc_dt.tzinfo is None:
        utc_dt = pytz.utc.localize(utc_dt)
    malaysia_time = utc_dt.astimezone(malaysia_tz)
    return malaysia_time

@analytics_bp.route('/analytics')
@login_required
def analytics():
    # Get data for filters
    categories = Category.query.all()
    priorities = Priority.query.all()
    statuses = Status.query.all()
    reported_by_options = ReportedBy.query.all()
    types = Type.query.all()

    # Get accessible units for current user
    units = get_accessible_units_query().all()

    return render_template('analytics_reporting.html',
                           categories=categories,
                           priorities=priorities,
                           statuses=statuses,
                           units=units,
                           reported_by_options=reported_by_options,
                           types=types
    )


@analytics_bp.route('/api/analytics/issues')
@login_required
def get_analytics_issues():
    # Get filter parameters
    days = request.args.get('days', type=int)
    time_filter = request.args.get('time_filter')
    category_id = request.args.get('category_id', type=int)
    issue_item_id = request.args.get('issue_item_id', type=int)
    priority_id = request.args.get('priority_id', type=int)
    status_id = request.args.get('status_id', type=int)
    unit = request.args.get('unit')
    reported_by_id = request.args.get('reported_by_id', type=int)
    type_id = request.args.get('type_id', type=int)
    view_type = request.args.get('view_type')

    # Start with accessible issues query
    query = get_accessible_issues_query()

    # Apply date filter with updated calendar-based logic
    if days:
        # Standard days-based filtering (kept for backward compatibility)
        date_threshold = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Issue.date_added >= date_threshold)
    elif time_filter:
        # Enhanced time filters
        now = datetime.utcnow()
        malaysia_tz = pytz.timezone('Asia/Kuala_Lumpur')
        now_local = now.replace(tzinfo=pytz.utc).astimezone(malaysia_tz)

        if time_filter == 'hour':
            # Last 1 hour
            hour_ago = now - timedelta(hours=1)
            query = query.filter(Issue.date_added >= hour_ago)

        elif time_filter == 'today':
            # Today (00:00:00 to now)
            today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            today_start_utc = today_start.astimezone(pytz.utc)
            query = query.filter(Issue.date_added >= today_start_utc)

        elif time_filter == 'yesterday':
            # Yesterday (00:00:00 to 23:59:59)
            yesterday_start = (now_local - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_end = yesterday_start.replace(hour=23, minute=59, second=59, microsecond=999999)
            yesterday_start_utc = yesterday_start.astimezone(pytz.utc)
            yesterday_end_utc = yesterday_end.astimezone(pytz.utc)
            query = query.filter(Issue.date_added >= yesterday_start_utc, Issue.date_added <= yesterday_end_utc)

        elif time_filter == 'this-week':
            # This week (Monday to now)
            days_since_monday = now_local.weekday()
            this_week_start = (now_local - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
            this_week_start_utc = this_week_start.astimezone(pytz.utc)
            query = query.filter(Issue.date_added >= this_week_start_utc)

        elif time_filter == 'last-week':
            # Last week (Monday to Sunday of previous week)
            days_since_monday = now_local.weekday()
            last_week_end = (now_local - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
            last_week_start = (last_week_end - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
            last_week_start_utc = last_week_start.astimezone(pytz.utc)
            last_week_end_utc = last_week_end.astimezone(pytz.utc)
            query = query.filter(Issue.date_added >= last_week_start_utc, Issue.date_added <= last_week_end_utc)

        elif time_filter == 'this-month':
            # This month (1st day to now)
            this_month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            this_month_start_utc = this_month_start.astimezone(pytz.utc)
            query = query.filter(Issue.date_added >= this_month_start_utc)

        elif time_filter == 'last-month':
            # Last month (1st day to last day of previous month)
            this_month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            last_month_end = this_month_start - timedelta(seconds=1)
            last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            last_month_start_utc = last_month_start.astimezone(pytz.utc)
            last_month_end_utc = last_month_end.astimezone(pytz.utc)
            query = query.filter(Issue.date_added >= last_month_start_utc, Issue.date_added <= last_month_end_utc)

        elif time_filter == 'this-year':
            # This year (January 1st to now)
            this_year_start = now_local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            this_year_start_utc = this_year_start.astimezone(pytz.utc)
            query = query.filter(Issue.date_added >= this_year_start_utc)

        elif time_filter == 'last-year':
            # Last year (January 1st to December 31st of previous year)
            last_year_start = now_local.replace(year=now_local.year-1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            last_year_end = now_local.replace(year=now_local.year-1, month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
            last_year_start_utc = last_year_start.astimezone(pytz.utc)
            last_year_end_utc = last_year_end.astimezone(pytz.utc)
            query = query.filter(Issue.date_added >= last_year_start_utc, Issue.date_added <= last_year_end_utc)

    # Apply other filters if specified (keep existing logic)
    if category_id:
        query = query.filter_by(category_id=category_id)

    if issue_item_id:
        query = query.filter_by(issue_item_id=issue_item_id)

    if priority_id:
        query = query.filter_by(priority_id=priority_id)

    if status_id:
        query = query.filter_by(status_id=status_id)

    if unit:
        query = query.filter_by(unit=unit)

    if reported_by_id:
        query = query.filter_by(reported_by_id=reported_by_id)

    if type_id:
        query = query.filter_by(type_id=type_id)

    # Execute query
    issues = query.all()

    # Convert to serializable format with related data (rest remains the same)
    result = []
    for issue in issues:
        # Convert UTC date to Malaysia time before sending to frontend
        malaysia_date = convert_utc_to_malaysia_time(issue.date_added)

        issue_data = {
            'id': issue.id,
            'description': issue.description,
            'unit': issue.unit,
            'date_added': malaysia_date.isoformat() if malaysia_date else None,  # This is the key change
            'solution': issue.solution,
            'guest_name': issue.guest_name,
            'cost': float(issue.cost) if issue.cost else None,
            'assigned_to': issue.assigned_to,

            # Include related data
            'category_id': issue.category_id,
            'category_name': issue.category.name if issue.category else None,

            'reported_by_id': issue.reported_by_id,
            'reported_by_name': issue.reported_by.name if issue.reported_by else None,

            'priority_id': issue.priority_id,
            'priority_name': issue.priority.name if issue.priority else None,

            'status_id': issue.status_id,
            'status_name': issue.status.name if issue.status else None,

            'type_id': issue.type_id,
            'type_name': issue.type.name if issue.type else None,

            'issue_item_id': issue.issue_item_id,
            'issue_item_name': issue.issue_item.name if issue.issue_item else None,
        }
        result.append(issue_data)

    return jsonify(result)


@analytics_bp.route('/api/analytics/summary')
@login_required
def get_analytics_summary():
    company_id = current_user.company_id

    # Get accessible issues instead of all company issues
    accessible_issues = get_accessible_issues_query()
    total_issues = accessible_issues.count()

    # Get open issues count (Pending or In Progress) from accessible issues
    pending_status = Status.query.filter_by(name='Pending').first()
    in_progress_status = Status.query.filter_by(name='In Progress').first()

    open_issues_filter = []
    if pending_status:
        open_issues_filter.append(Issue.status_id == pending_status.id)
    if in_progress_status:
        open_issues_filter.append(Issue.status_id == in_progress_status.id)

    open_issues = 0
    if open_issues_filter:
        open_issues = accessible_issues.filter(db.or_(*open_issues_filter)).count()

    # Get resolved issues count from accessible issues
    resolved_status = Status.query.filter_by(name='Resolved').first()
    resolved_issues = 0
    if resolved_status:
        resolved_issues = accessible_issues.filter_by(status_id=resolved_status.id).count()

    # Calculate average cost from accessible issues
    avg_cost_result = accessible_issues.filter(Issue.cost.isnot(None)).with_entities(func.avg(Issue.cost)).scalar()
    avg_cost = float(avg_cost_result) if avg_cost_result else 0

    # Get top issue categories from accessible issues
    accessible_unit_ids = current_user.get_accessible_unit_ids()
    if accessible_unit_ids:
        category_counts = db.session.query(
            Category.name,
            func.count(Issue.id).label('count')
        ).join(
            Issue, Issue.category_id == Category.id
        ).filter(
            Issue.company_id == company_id,
            Issue.unit_id.in_(accessible_unit_ids)
        ).group_by(
            Category.name
        ).order_by(
            func.count(Issue.id).desc()
        ).limit(5).all()
    else:
        category_counts = []

    top_categories = [{'name': name, 'count': count} for name, count in category_counts]

    # Return JSON summary
    return jsonify({
        'total_issues': total_issues,
        'open_issues': open_issues,
        'resolved_issues': resolved_issues,
        'avg_cost': avg_cost,
        'top_categories': top_categories
    })