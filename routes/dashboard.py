from flask import Blueprint, render_template, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func, and_, extract
from models import (db, Issue, Unit, Category, Priority, Status, Type, ReportedBy,
                    BookingForm, ExpenseData, IssueItem)
from flask import request
import pytz
from utils.access_control import (
    get_accessible_units_query,
    get_accessible_bookings_query,
    get_accessible_issues_query
)

dashboard_bp = Blueprint('dashboard', __name__)


# Add template filters
@dashboard_bp.app_template_filter('month_name')
def month_name_filter(month_num):
    months = [
        '', 'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]
    return months[month_num] if 1 <= month_num <= 12 else str(month_num)


@dashboard_bp.app_template_filter('get_color')
def get_color_filter(index):
    colors = [
        '#8B5A96', '#7B68A6', '#6B78B6', '#5B88C6', '#4B98D6',
        '#3BA8E6', '#2BB8F6', '#1BC8FF', '#0BD8FF', '#00E8FF'
    ]
    return colors[index % len(colors)]


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    # Redirect cleaners to cleaner dashboard
    if current_user.is_cleaner:
        return redirect(url_for('cleaners.cleaner_dashboard'))

    # Get current user's company ID
    user_company_id = current_user.company_id

    # Get current date info
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    current_month = datetime.now().month
    current_year = datetime.now().year

    # ============ BOOKING ANALYTICS ============
    booking_stats = {}

    if current_user.has_permission('can_view_bookings'):
        # Get accessible ACTIVE units for this user
        accessible_active_units = get_accessible_units_query().filter(Unit.is_occupied == True).all()
        accessible_unit_ids = [unit.id for unit in accessible_active_units]

        if accessible_unit_ids:
            # Total accessible ACTIVE units
            total_units = len(accessible_unit_ids)

            # Current occupancy (check-in <= today < check-out) for accessible active units
            current_occupancy = BookingForm.query.filter(
                BookingForm.company_id == user_company_id,
                BookingForm.unit_id.in_(accessible_unit_ids),
                BookingForm.check_in_date <= today,
                BookingForm.check_out_date > today
            ).count()

            # Tomorrow occupancy for accessible active units
            tomorrow_occupancy = BookingForm.query.filter(
                BookingForm.company_id == user_company_id,
                BookingForm.unit_id.in_(accessible_unit_ids),
                BookingForm.check_in_date <= tomorrow,
                BookingForm.check_out_date > tomorrow
            ).count()

            # Revenue today (bookings checking in today) for accessible active units
            today_bookings = BookingForm.query.filter(
                BookingForm.company_id == user_company_id,
                BookingForm.unit_id.in_(accessible_unit_ids),
                BookingForm.check_in_date == today
            ).all()
            revenue_today = sum(float(booking.price) for booking in today_bookings if booking.price)

            # Revenue tomorrow for accessible active units
            tomorrow_bookings = BookingForm.query.filter(
                BookingForm.company_id == user_company_id,
                BookingForm.unit_id.in_(accessible_unit_ids),
                BookingForm.check_in_date == tomorrow
            ).all()
            revenue_tomorrow = sum(float(booking.price) for booking in tomorrow_bookings if booking.price)

            # Check-ins and check-outs for accessible active units
            checkins_today = len(today_bookings)
            checkins_tomorrow = BookingForm.query.filter(
                BookingForm.company_id == user_company_id,
                BookingForm.unit_id.in_(accessible_unit_ids),
                BookingForm.check_in_date == tomorrow
            ).count()

            checkouts_today = BookingForm.query.filter(
                BookingForm.company_id == user_company_id,
                BookingForm.unit_id.in_(accessible_unit_ids),
                BookingForm.check_out_date == today
            ).count()

            checkouts_tomorrow = BookingForm.query.filter(
                BookingForm.company_id == user_company_id,
                BookingForm.unit_id.in_(accessible_unit_ids),
                BookingForm.check_out_date == tomorrow
            ).count()

            booking_stats = {
                'total_units': total_units,
                'current_occupancy': current_occupancy,
                'tomorrow_occupancy': tomorrow_occupancy,
                'revenue_today': revenue_today,
                'revenue_tomorrow': revenue_tomorrow,
                'checkins_today': checkins_today,
                'checkins_tomorrow': checkins_tomorrow,
                'checkouts_today': checkouts_today,
                'checkouts_tomorrow': checkouts_tomorrow
            }
        else:
            # No accessible active units
            booking_stats = {
                'total_units': 0,
                'current_occupancy': 0,
                'tomorrow_occupancy': 0,
                'revenue_today': 0,
                'revenue_tomorrow': 0,
                'checkins_today': 0,
                'checkins_tomorrow': 0,
                'checkouts_today': 0,
                'checkouts_tomorrow': 0
            }

    # ============ ISSUE ANALYTICS ============
    issue_stats = {}

    if current_user.has_permission('can_view_issues'):
        # Get accessible unit IDs
        accessible_unit_ids = current_user.get_accessible_unit_ids()

        if accessible_unit_ids:
            # Issues by status for accessible units
            issues_by_status_query = db.session.query(
                Status.name, func.count(Issue.id).label('count')
            ).join(Issue, Issue.status_id == Status.id) \
                .filter(
                Issue.company_id == user_company_id,
                Issue.unit_id.in_(accessible_unit_ids)
            ) \
                .group_by(Status.name).all()

            # Convert to dictionary for easier template usage
            status_data = {status: count for status, count in issues_by_status_query}

            # Top 10 issue types (by issue_item) for accessible units
            top_issue_types_query = db.session.query(
                IssueItem.name, func.count(Issue.id).label('count')
            ).join(Issue, Issue.issue_item_id == IssueItem.id) \
                .filter(
                Issue.company_id == user_company_id,
                Issue.unit_id.in_(accessible_unit_ids)
            ) \
                .group_by(IssueItem.name) \
                .order_by(func.count(Issue.id).desc()) \
                .limit(10).all()

            # Convert to list of tuples for JSON serialization
            top_issue_types = [(name, count) for name, count in top_issue_types_query]

            # Issues by unit and category for heatmap (accessible units only)
            accessible_units = get_accessible_units_query().all()
            categories = Category.query.all()

            heatmap_data = {}
            for unit in accessible_units:
                heatmap_data[unit.unit_number] = {}
                for category in categories:
                    count = Issue.query.filter(
                        Issue.company_id == user_company_id,
                        Issue.unit_id == unit.id,
                        Issue.category_id == category.id
                    ).count()
                    heatmap_data[unit.unit_number][category.name] = count

            issue_stats = {
                'status_data': status_data,
                'top_issue_types': top_issue_types,
                'heatmap_data': heatmap_data,
                'units': [unit.unit_number for unit in accessible_units],
                'categories': [cat.name for cat in categories]
            }
        else:
            # No accessible units
            issue_stats = {
                'status_data': {},
                'top_issue_types': [],
                'heatmap_data': {},
                'units': [],
                'categories': []
            }

    # ============ EXPENSES ANALYTICS ============
    expense_stats = {}

    # Get accessible unit IDs for expense filtering
    accessible_unit_ids = current_user.get_accessible_unit_ids()

    if accessible_unit_ids:
        # Get current month expenses for accessible units
        current_month_expenses = ExpenseData.query.filter(
            ExpenseData.company_id == user_company_id,
            ExpenseData.unit_id.in_(accessible_unit_ids),
            ExpenseData.year == current_year,
            ExpenseData.month == current_month
        ).all()

        # Get previous month for comparison
        prev_month = current_month - 1 if current_month > 1 else 12
        prev_year = current_year if current_month > 1 else current_year - 1

        prev_month_expenses = ExpenseData.query.filter(
            ExpenseData.company_id == user_company_id,
            ExpenseData.unit_id.in_(accessible_unit_ids),
            ExpenseData.year == prev_year,
            ExpenseData.month == prev_month
        ).all()

        # Calculate totals (keep existing calculation logic)
        def calculate_totals(expenses_list):
            totals = {
                'revenue': 0,
                'total_expenses': 0,
                'rental': 0,
                'electricity': 0,
                'water': 0,
                'sewage': 0,
                'internet': 0,
                'cleaner': 0,
                'laundry': 0,
                'supplies': 0,
                'repair': 0,
                'replace': 0,
                'other': 0
            }

            for expense in expenses_list:
                sales = float(expense.sales or 0)
                rental = float(expense.rental or 0)
                electricity = float(expense.electricity or 0)
                water = float(expense.water or 0)
                sewage = float(expense.sewage or 0)
                internet = float(expense.internet or 0)
                cleaner = float(expense.cleaner or 0)
                laundry = float(expense.laundry or 0)
                supplies = float(expense.supplies or 0)
                repair = float(expense.repair or 0)
                replace = float(expense.replace or 0)
                other = float(expense.other or 0)

                totals['revenue'] += sales
                totals['rental'] += rental
                totals['electricity'] += electricity
                totals['water'] += water
                totals['sewage'] += sewage
                totals['internet'] += internet
                totals['cleaner'] += cleaner
                totals['laundry'] += laundry
                totals['supplies'] += supplies
                totals['repair'] += repair
                totals['replace'] += replace
                totals['other'] += other

                totals['total_expenses'] += (rental + electricity + water + sewage +
                                             internet + cleaner + laundry + supplies +
                                             repair + replace + other)

            totals['net_income'] = totals['revenue'] - totals['total_expenses']
            return totals

        current_totals = calculate_totals(current_month_expenses)
        prev_totals = calculate_totals(prev_month_expenses)

        # Calculate percentage changes (keep existing logic)
        def calc_percentage_change(current, previous):
            if previous == 0:
                return 100 if current > 0 else 0
            return ((current - previous) / previous) * 100

        revenue_change = calc_percentage_change(current_totals['revenue'], prev_totals['revenue'])
        expense_change = calc_percentage_change(current_totals['total_expenses'], prev_totals['total_expenses'])
        income_change = calc_percentage_change(current_totals['net_income'], prev_totals['net_income'])

        # Expense breakdown for pie chart (keep existing logic)
        expense_breakdown = []
        for category in ['rental', 'electricity', 'water', 'sewage', 'internet', 'cleaner', 'laundry', 'supplies',
                         'repair',
                         'replace', 'other']:
            if current_totals[category] > 0:
                percentage = (current_totals[category] / current_totals['total_expenses']) * 100 if current_totals[
                                                                                                        'total_expenses'] > 0 else 0
                expense_breakdown.append({
                    'category': category.title(),
                    'amount': current_totals[category],
                    'percentage': percentage
                })

        # Sort by amount (highest first)
        expense_breakdown.sort(key=lambda x: x['amount'], reverse=True)

        expense_stats = {
            'current_month': current_month,
            'current_year': current_year,
            'revenue': current_totals['revenue'],
            'total_expenses': current_totals['total_expenses'],
            'net_income': current_totals['net_income'],
            'revenue_change': revenue_change,
            'expense_change': expense_change,
            'income_change': income_change,
            'expense_breakdown': expense_breakdown
        }
    else:
        # No accessible units
        expense_stats = {
            'current_month': current_month,
            'current_year': current_year,
            'revenue': 0,
            'total_expenses': 0,
            'net_income': 0,
            'revenue_change': 0,
            'expense_change': 0,
            'income_change': 0,
            'expense_breakdown': []
        }

    return render_template('dashboard.html',
                           booking_stats=booking_stats,
                           issue_stats=issue_stats,
                           expense_stats=expense_stats)


@dashboard_bp.route('/api/dashboard/chart-data')
@login_required
def get_chart_data():
    """API endpoint to get chart data for dashboard"""
    user_company_id = current_user.company_id

    # Get accessible unit IDs
    accessible_unit_ids = current_user.get_accessible_unit_ids()

    if not accessible_unit_ids:
        # No accessible units - return empty data
        return jsonify({
            'status_data': [],
            'issue_types_data': []
        })

    # Get issue status data for accessible units only
    issues_by_status_query = db.session.query(
        Status.name, func.count(Issue.id).label('count')
    ).join(Issue, Issue.status_id == Status.id) \
        .filter(
        Issue.company_id == user_company_id,
        Issue.unit_id.in_(accessible_unit_ids)
    ) \
        .group_by(Status.name).all()

    status_data = [{'name': status, 'count': count} for status, count in issues_by_status_query]

    # Get top issue types for accessible units only
    top_issue_types_query = db.session.query(
        IssueItem.name, func.count(Issue.id).label('count')
    ).join(Issue, Issue.issue_item_id == IssueItem.id) \
        .filter(
        Issue.company_id == user_company_id,
        Issue.unit_id.in_(accessible_unit_ids)
    ) \
        .group_by(IssueItem.name) \
        .order_by(func.count(Issue.id).desc()) \
        .limit(10).all()

    issue_types_data = [{'name': name, 'count': count} for name, count in top_issue_types_query]

    return jsonify({
        'status_data': status_data,
        'issue_types_data': issue_types_data
    })


@dashboard_bp.route('/api/dashboard/earnings')
@login_required
def get_earnings_data():
    """API endpoint to get earnings data with date and unit filtering"""
    # Get current user's company ID
    user_company_id = current_user.company_id

    # Get filter parameters
    time_filter = request.args.get('time_filter', 'this-month')
    unit_filter = request.args.get('unit_filter', 'all')

    # Get accessible unit IDs
    accessible_unit_ids = current_user.get_accessible_unit_ids()

    if not accessible_unit_ids:
        # No accessible units - return zero data
        return jsonify({
            'revenue': 0,
            'total_expenses': 0,
            'net_income': 0,
            'revenue_change': 0,
            'expense_change': 0,
            'income_change': 0,
            'expense_breakdown': []
        })

    # If unit_filter is specified and user has access, use it; otherwise use all accessible units
    if unit_filter != 'all' and int(unit_filter) in accessible_unit_ids:
        filtered_unit_ids = [int(unit_filter)]
    else:
        filtered_unit_ids = accessible_unit_ids

    # FIXED: Use the same date calculation as bookings page
    now = datetime.now()

    # Calculate date range for current period using local time (same as bookings page)
    start_date, end_date = calculate_date_range_fixed(time_filter, now)

    # Calculate date range for previous period
    prev_start_date, prev_end_date = calculate_previous_period_range_fixed(time_filter, now)

    # Get expense data for current period with accessible unit filtering
    if time_filter in ['today', 'yesterday']:
        current_data = calculate_daily_earnings_fixed(user_company_id, start_date, end_date, filtered_unit_ids)
        previous_data = calculate_daily_earnings_fixed(user_company_id, prev_start_date, prev_end_date,
                                                       filtered_unit_ids)
    elif time_filter in ['this-week', 'last-week']:
        current_data = calculate_weekly_earnings(user_company_id, start_date, end_date, filtered_unit_ids)
        previous_data = calculate_weekly_earnings(user_company_id, prev_start_date, prev_end_date, filtered_unit_ids)
    elif time_filter in ['this-month', 'last-month']:
        current_data = calculate_monthly_earnings(user_company_id, start_date, end_date, filtered_unit_ids)
        previous_data = calculate_monthly_earnings(user_company_id, prev_start_date, prev_end_date, filtered_unit_ids)
    elif time_filter in ['this-year', 'last-year']:
        current_data = calculate_yearly_earnings(user_company_id, start_date, end_date, filtered_unit_ids)
        previous_data = calculate_yearly_earnings(user_company_id, prev_start_date, prev_end_date, filtered_unit_ids)
    else:
        current_data = calculate_monthly_earnings(user_company_id, start_date, end_date, filtered_unit_ids)
        previous_data = calculate_monthly_earnings(user_company_id, prev_start_date, prev_end_date, filtered_unit_ids)

    # Calculate percentage changes
    revenue_change = calculate_percentage_change(previous_data['revenue'], current_data['revenue'])
    expense_change = calculate_percentage_change(previous_data['total_expenses'], current_data['total_expenses'])
    income_change = calculate_percentage_change(previous_data['net_income'], current_data['net_income'])

    # Add percentage changes to current data
    current_data['revenue_change'] = revenue_change
    current_data['expense_change'] = expense_change
    current_data['income_change'] = income_change

    return jsonify(current_data)


def calculate_percentage_change(old_value, new_value):
    """Calculate percentage change between two values"""
    if old_value == 0:
        return 100.0 if new_value > 0 else 0.0
    return ((new_value - old_value) / old_value) * 100


def calculate_previous_period_range(time_filter, now_local):
    """Calculate start and end dates for the previous period"""

    if time_filter == 'today':
        # Previous period is yesterday
        yesterday = now_local - timedelta(days=1)
        start_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)

    elif time_filter == 'yesterday':
        # Previous period is day before yesterday
        day_before = now_local - timedelta(days=2)
        start_date = day_before.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = day_before.replace(hour=23, minute=59, second=59, microsecond=999999)

    elif time_filter == 'this-week':
        # Previous period is last week
        days_since_monday = now_local.weekday()
        last_week_start = (now_local - timedelta(days=days_since_monday + 7)).replace(hour=0, minute=0, second=0,
                                                                                      microsecond=0)
        last_week_end = (now_local - timedelta(days=days_since_monday + 1)).replace(hour=23, minute=59, second=59,
                                                                                    microsecond=999999)
        start_date = last_week_start
        end_date = last_week_end

    elif time_filter == 'last-week':
        # Previous period is week before last week
        days_since_monday = now_local.weekday()
        prev_week_start = (now_local - timedelta(days=days_since_monday + 14)).replace(hour=0, minute=0, second=0,
                                                                                       microsecond=0)
        prev_week_end = (now_local - timedelta(days=days_since_monday + 8)).replace(hour=23, minute=59, second=59,
                                                                                    microsecond=999999)
        start_date = prev_week_start
        end_date = prev_week_end

    elif time_filter == 'this-month':
        # Previous period is last month
        last_month_start = (now_local.replace(day=1) - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0,
                                                                                  microsecond=0)
        last_month_end = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
        start_date = last_month_start
        end_date = last_month_end

    elif time_filter == 'last-month':
        # Previous period is month before last month
        current_month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = (current_month_start - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0,
                                                                             microsecond=0)
        prev_month_start = (last_month_start - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0,
                                                                          microsecond=0)
        prev_month_end = last_month_start - timedelta(seconds=1)
        start_date = prev_month_start
        end_date = prev_month_end

    elif time_filter == 'this-year':
        # Previous period is last year
        last_year_start = now_local.replace(year=now_local.year - 1, month=1, day=1, hour=0, minute=0, second=0,
                                            microsecond=0)
        last_year_end = now_local.replace(year=now_local.year - 1, month=12, day=31, hour=23, minute=59, second=59,
                                          microsecond=999999)
        start_date = last_year_start
        end_date = last_year_end

    elif time_filter == 'last-year':
        # Previous period is year before last year
        prev_year_start = now_local.replace(year=now_local.year - 2, month=1, day=1, hour=0, minute=0, second=0,
                                            microsecond=0)
        prev_year_end = now_local.replace(year=now_local.year - 2, month=12, day=31, hour=23, minute=59, second=59,
                                          microsecond=999999)
        start_date = prev_year_start
        end_date = prev_year_end

    else:
        # Default to last month
        last_month_start = (now_local.replace(day=1) - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0,
                                                                                  microsecond=0)
        last_month_end = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
        start_date = last_month_start
        end_date = last_month_end

    return start_date, end_date


def calculate_date_range(time_filter, now_local):
    """Calculate start and end dates based on time filter"""

    # FIXED: Ensure we're working with Malaysia timezone consistently
    print(f"DEBUG: calculate_date_range called with time_filter='{time_filter}', now_local={now_local}")

    if time_filter == 'today':
        # FIXED: Use Malaysia timezone date boundaries
        start_date = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)
        print(f"DEBUG: Today range - start: {start_date}, end: {end_date}")

    elif time_filter == 'yesterday':
        # FIXED: Calculate yesterday in Malaysia timezone
        yesterday = now_local - timedelta(days=1)
        start_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        print(f"DEBUG: Yesterday range - start: {start_date}, end: {end_date}")

    elif time_filter == 'this-week':
        days_since_monday = now_local.weekday()
        start_date = (now_local - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)

    elif time_filter == 'last-week':
        days_since_monday = now_local.weekday()
        last_week_end = (now_local - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0,
                                                                                microsecond=0) - timedelta(seconds=1)
        last_week_start = (last_week_end - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = last_week_start
        end_date = last_week_end

    elif time_filter == 'this-month':
        start_date = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)

    elif time_filter == 'last-month':
        last_month_start = (now_local.replace(day=1) - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0,
                                                                                  microsecond=0)
        last_month_end = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
        start_date = last_month_start
        end_date = last_month_end

    elif time_filter == 'this-year':
        start_date = now_local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)

    elif time_filter == 'last-year':
        last_year_start = now_local.replace(year=now_local.year - 1, month=1, day=1, hour=0, minute=0, second=0,
                                            microsecond=0)
        last_year_end = now_local.replace(year=now_local.year - 1, month=12, day=31, hour=23, minute=59, second=59,
                                          microsecond=999999)
        start_date = last_year_start
        end_date = last_year_end

    else:
        # Default to this month
        start_date = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)

    print(f"DEBUG: Final date range - start: {start_date.date()}, end: {end_date.date()}")
    return start_date, end_date


def calculate_daily_earnings_fixed(company_id, start_date, end_date, unit_ids):
    """Calculate earnings for daily periods - FIXED to match bookings page exactly"""

    print(f"DEBUG: calculate_daily_earnings_fixed - filtering for date: {start_date}")

    # FIXED: Use exact same query as bookings page
    bookings_query = BookingForm.query.filter(
        BookingForm.company_id == company_id,
        BookingForm.unit_id.in_(unit_ids),
        BookingForm.check_in_date == start_date  # Exact date match like bookings page
    )

    bookings = bookings_query.all()
    total_revenue = sum(float(booking.price) for booking in bookings if booking.price)

    print(f"DEBUG: Found {len(bookings)} bookings for {start_date}, total revenue: {total_revenue}")

    # For daily earnings, we don't usually have issues costs, so keep it simple
    total_expenses = 0
    expense_breakdown = []

    return {
        'revenue': total_revenue,
        'total_expenses': total_expenses,
        'net_income': total_revenue - total_expenses,
        'expense_breakdown': expense_breakdown
    }


def calculate_date_range_fixed(time_filter, now):
    """Calculate start and end dates based on time filter - FIXED to match bookings page"""

    print(f"DEBUG: calculate_date_range_fixed called with time_filter='{time_filter}', now={now}")

    if time_filter == 'today':
        # FIXED: Use the same logic as bookings page
        today = now.date()
        start_date = today
        end_date = today
        print(f"DEBUG: Today - date: {today}")

    elif time_filter == 'yesterday':
        # FIXED: Use the same logic as bookings page
        today = now.date()
        yesterday = today - timedelta(days=1)
        start_date = yesterday
        end_date = yesterday
        print(f"DEBUG: Yesterday - date: {yesterday}")

    elif time_filter == 'this-week':
        # FIXED: Calculate this week properly (Monday to Sunday of current week)
        today = now.date()
        days_since_monday = today.weekday()  # Monday = 0, Sunday = 6
        monday_this_week = today - timedelta(days=days_since_monday)
        sunday_this_week = monday_this_week + timedelta(days=6)
        start_date = monday_this_week
        end_date = sunday_this_week
        print(f"DEBUG: This week - start: {start_date}, end: {end_date}")

    elif time_filter == 'last-week':
        # FIXED: Calculate last week properly (Monday to Sunday of previous week)
        today = now.date()
        days_since_monday = today.weekday()
        monday_this_week = today - timedelta(days=days_since_monday)
        sunday_last_week = monday_this_week - timedelta(days=1)
        monday_last_week = sunday_last_week - timedelta(days=6)
        start_date = monday_last_week
        end_date = sunday_last_week
        print(f"DEBUG: Last week - start: {start_date}, end: {end_date}")

    elif time_filter == 'this-month':
        import calendar
        today = now.date()
        start_date = today.replace(day=1)
        # Get last day of current month
        last_day_of_month = calendar.monthrange(today.year, today.month)[1]
        end_date = today.replace(day=last_day_of_month)

    elif time_filter == 'last-month':
        today = now.date()
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        start_date = last_month_end.replace(day=1)
        end_date = last_month_end

    elif time_filter == 'this-year':
        today = now.date()
        start_date = today.replace(month=1, day=1)
        end_date = today.replace(month=12, day=31)

    elif time_filter == 'last-year':
        today = now.date()
        start_date = today.replace(year=today.year - 1, month=1, day=1)
        end_date = today.replace(year=today.year - 1, month=12, day=31)

    else:
        # Default to this month
        today = now.date()
        start_date = today.replace(day=1)
        end_date = today

    print(f"DEBUG: Final date range - start: {start_date}, end: {end_date}")
    return start_date, end_date


def calculate_previous_period_range_fixed(time_filter, now):
    """Calculate start and end dates for the previous period - FIXED"""

    today = now.date()

    if time_filter == 'today':
        # Previous period is yesterday
        yesterday = today - timedelta(days=1)
        start_date = yesterday
        end_date = yesterday

    elif time_filter == 'yesterday':
        # Previous period is day before yesterday
        day_before = today - timedelta(days=2)
        start_date = day_before
        end_date = day_before

    elif time_filter == 'this-week':
        # Previous period is last week (Monday to Sunday of previous complete week)
        days_since_monday = today.weekday()
        monday_this_week = today - timedelta(days=days_since_monday)
        sunday_last_week = monday_this_week - timedelta(days=1)
        monday_last_week = sunday_last_week - timedelta(days=6)
        start_date = monday_last_week
        end_date = sunday_last_week

    elif time_filter == 'last-week':
        # Previous period is week before last week
        days_since_monday = today.weekday()
        monday_this_week = today - timedelta(days=days_since_monday)
        sunday_last_week = monday_this_week - timedelta(days=1)
        monday_last_week = sunday_last_week - timedelta(days=6)
        # Week before last week
        sunday_two_weeks_ago = monday_last_week - timedelta(days=1)
        monday_two_weeks_ago = sunday_two_weeks_ago - timedelta(days=6)
        start_date = monday_two_weeks_ago
        end_date = sunday_two_weeks_ago

    elif time_filter == 'this-month':
        # Previous period is last month
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        start_date = last_month_end.replace(day=1)
        end_date = last_month_end

    elif time_filter == 'last-month':
        # Previous period is month before last month
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        first_of_last_month = last_month_end.replace(day=1)
        prev_month_end = first_of_last_month - timedelta(days=1)
        start_date = prev_month_end.replace(day=1)
        end_date = prev_month_end

    elif time_filter == 'this-year':
        # Previous period is last year
        start_date = today.replace(year=today.year - 1, month=1, day=1)
        end_date = today.replace(year=today.year - 1, month=12, day=31)

    elif time_filter == 'last-year':
        # Previous period is year before last year
        start_date = today.replace(year=today.year - 2, month=1, day=1)
        end_date = today.replace(year=today.year - 2, month=12, day=31)

    else:
        # Default to last month
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        start_date = last_month_end.replace(day=1)
        end_date = last_month_end

    return start_date, end_date


def calculate_weekly_earnings(company_id, start_date, end_date, unit_ids):
    """Calculate earnings for weekly periods - FIXED to sum up daily revenues"""

    print(f"DEBUG: calculate_weekly_earnings - start_date: {start_date}, end_date: {end_date}")

    # FIXED: For weekly periods, we need to sum up all check-ins within the date range
    bookings_query = BookingForm.query.filter(
        BookingForm.company_id == company_id,
        BookingForm.unit_id.in_(unit_ids),
        BookingForm.check_in_date >= start_date,
        BookingForm.check_in_date <= end_date
    )

    bookings = bookings_query.all()
    total_revenue = sum(float(booking.price) for booking in bookings if booking.price)

    print(f"DEBUG: Found {len(bookings)} bookings for week {start_date} to {end_date}, total revenue: {total_revenue}")

    # Base query for issues costs within the week
    issues_query = Issue.query.filter(
        Issue.company_id == company_id,
        Issue.unit_id.in_(unit_ids)
    )

    # For issues, we need to filter by datetime (date_added field)
    # Convert dates to datetime for proper comparison
    from datetime import datetime, time
    start_datetime = datetime.combine(start_date, time.min)
    end_datetime = datetime.combine(end_date, time.max)

    issues_query = issues_query.filter(
        Issue.date_added >= start_datetime,
        Issue.date_added <= end_datetime,
        Issue.cost.isnot(None)
    )

    issues_with_cost = issues_query.all()

    total_repair_cost = sum(
        float(issue.cost) for issue in issues_with_cost if issue.type and issue.type.name == 'Repair')
    total_replace_cost = sum(
        float(issue.cost) for issue in issues_with_cost if issue.type and issue.type.name == 'Replace')

    # Create expense breakdown
    expense_breakdown = []
    if total_repair_cost > 0:
        expense_breakdown.append({
            'category': 'Repair',
            'amount': total_repair_cost,
            'percentage': 100 * total_repair_cost / (total_repair_cost + total_replace_cost) if (
                                                                                                        total_repair_cost + total_replace_cost) > 0 else 0
        })

    if total_replace_cost > 0:
        expense_breakdown.append({
            'category': 'Replace',
            'amount': total_replace_cost,
            'percentage': 100 * total_replace_cost / (total_repair_cost + total_replace_cost) if (
                                                                                                         total_repair_cost + total_replace_cost) > 0 else 0
        })

    total_expenses = total_repair_cost + total_replace_cost

    return {
        'revenue': total_revenue,
        'total_expenses': total_expenses,
        'net_income': total_revenue - total_expenses,
        'expense_breakdown': expense_breakdown
    }


def calculate_monthly_earnings(company_id, start_date, end_date, unit_ids):
    """Calculate earnings for monthly periods using actual bookings for revenue and ExpenseData for expenses"""

    print(f"DEBUG: calculate_monthly_earnings - start_date: {start_date}, end_date: {end_date}")

    # REVENUE: Use actual bookings within the complete month range
    bookings_query = BookingForm.query.filter(
        BookingForm.company_id == company_id,
        BookingForm.unit_id.in_(unit_ids),
        BookingForm.check_in_date >= start_date,
        BookingForm.check_in_date <= end_date
    )

    bookings = bookings_query.all()
    total_revenue = sum(float(booking.price) for booking in bookings if booking.price)

    print(f"DEBUG: Found {len(bookings)} bookings for month {start_date} to {end_date}, total revenue: {total_revenue}")

    # EXPENSES: Use ExpenseData table (original logic)
    year = start_date.year
    month = start_date.month

    expense_query = ExpenseData.query.filter(
        ExpenseData.company_id == company_id,
        ExpenseData.unit_id.in_(unit_ids),
        ExpenseData.year == year,
        ExpenseData.month == month
    )

    monthly_expenses = expense_query.all()

    # Calculate totals from ExpenseData (original calculation logic)
    totals = {
        'total_expenses': 0,
        'rental': 0,
        'electricity': 0,
        'water': 0,
        'sewage': 0,
        'internet': 0,
        'cleaner': 0,
        'laundry': 0,
        'supplies': 0,
        'repair': 0,
        'replace': 0,
        'other': 0
    }

    for expense in monthly_expenses:
        rental = float(expense.rental or 0)
        electricity = float(expense.electricity or 0)
        water = float(expense.water or 0)
        sewage = float(expense.sewage or 0)
        internet = float(expense.internet or 0)
        cleaner = float(expense.cleaner or 0)
        laundry = float(expense.laundry or 0)
        supplies = float(expense.supplies or 0)
        repair = float(expense.repair or 0)
        replace = float(expense.replace or 0)
        other = float(expense.other or 0)

        totals['rental'] += rental
        totals['electricity'] += electricity
        totals['water'] += water
        totals['sewage'] += sewage
        totals['internet'] += internet
        totals['cleaner'] += cleaner
        totals['laundry'] += laundry
        totals['supplies'] += supplies
        totals['repair'] += repair
        totals['replace'] += replace
        totals['other'] += other

        totals['total_expenses'] += (rental + electricity + water + sewage +
                                     internet + cleaner + laundry + supplies +
                                     repair + replace + other)

    # Create expense breakdown (original logic)
    expense_breakdown = []
    categories = ['rental', 'electricity', 'water', 'sewage', 'internet', 'cleaner',
                  'laundry', 'supplies', 'repair', 'replace', 'other']

    for category in categories:
        if totals[category] > 0:
            percentage = (totals[category] / totals['total_expenses']) * 100 if totals['total_expenses'] > 0 else 0
            expense_breakdown.append({
                'category': category.title(),
                'amount': totals[category],
                'percentage': percentage
            })

    # Sort by amount (highest first)
    expense_breakdown.sort(key=lambda x: x['amount'], reverse=True)

    return {
        'revenue': total_revenue,
        'total_expenses': totals['total_expenses'],
        'net_income': total_revenue - totals['total_expenses'],
        'expense_breakdown': expense_breakdown
    }


def calculate_yearly_earnings(company_id, start_date, end_date, unit_ids):
    """Calculate earnings for yearly periods using actual bookings for revenue and ExpenseData for expenses"""

    print(f"DEBUG: calculate_yearly_earnings - start_date: {start_date}, end_date: {end_date}")

    # REVENUE: Use actual bookings within the complete year range
    bookings_query = BookingForm.query.filter(
        BookingForm.company_id == company_id,
        BookingForm.unit_id.in_(unit_ids),
        BookingForm.check_in_date >= start_date,
        BookingForm.check_in_date <= end_date
    )

    bookings = bookings_query.all()
    total_revenue = sum(float(booking.price) for booking in bookings if booking.price)

    print(f"DEBUG: Found {len(bookings)} bookings for year {start_date} to {end_date}, total revenue: {total_revenue}")

    # EXPENSES: Use ExpenseData table for all months in the year
    year = start_date.year

    expense_query = ExpenseData.query.filter(
        ExpenseData.company_id == company_id,
        ExpenseData.unit_id.in_(unit_ids),
        ExpenseData.year == year
    )

    yearly_expenses = expense_query.all()

    # Calculate totals from ExpenseData (original calculation logic)
    totals = {
        'total_expenses': 0,
        'rental': 0,
        'electricity': 0,
        'water': 0,
        'sewage': 0,
        'internet': 0,
        'cleaner': 0,
        'laundry': 0,
        'supplies': 0,
        'repair': 0,
        'replace': 0,
        'other': 0
    }

    for expense in yearly_expenses:
        rental = float(expense.rental or 0)
        electricity = float(expense.electricity or 0)
        water = float(expense.water or 0)
        sewage = float(expense.sewage or 0)
        internet = float(expense.internet or 0)
        cleaner = float(expense.cleaner or 0)
        laundry = float(expense.laundry or 0)
        supplies = float(expense.supplies or 0)
        repair = float(expense.repair or 0)
        replace = float(expense.replace or 0)
        other = float(expense.other or 0)

        totals['rental'] += rental
        totals['electricity'] += electricity
        totals['water'] += water
        totals['sewage'] += sewage
        totals['internet'] += internet
        totals['cleaner'] += cleaner
        totals['laundry'] += laundry
        totals['supplies'] += supplies
        totals['repair'] += repair
        totals['replace'] += replace
        totals['other'] += other

        totals['total_expenses'] += (rental + electricity + water + sewage +
                                     internet + cleaner + laundry + supplies +
                                     repair + replace + other)

    # Create expense breakdown (original logic)
    expense_breakdown = []
    categories = ['rental', 'electricity', 'water', 'sewage', 'internet', 'cleaner',
                  'laundry', 'supplies', 'repair', 'replace', 'other']

    for category in categories:
        if totals[category] > 0:
            percentage = (totals[category] / totals['total_expenses']) * 100 if totals['total_expenses'] > 0 else 0
            expense_breakdown.append({
                'category': category.title(),
                'amount': totals[category],
                'percentage': percentage
            })

    # Sort by amount (highest first)
    expense_breakdown.sort(key=lambda x: x['amount'], reverse=True)

    return {
        'revenue': total_revenue,
        'total_expenses': totals['total_expenses'],
        'net_income': total_revenue - totals['total_expenses'],
        'expense_breakdown': expense_breakdown
    }