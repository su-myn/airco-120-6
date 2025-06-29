from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from models import db, ExpenseData, Unit, BookingForm, Issue, Type, ExpenseRemark
import json
from utils.access_control import (
    filter_query_by_accessible_units,
    get_accessible_units_query,
    get_accessible_bookings_query,
    get_accessible_issues_query,
    check_unit_access,
    require_unit_access
)

expenses_bp = Blueprint('expenses', __name__)


@expenses_bp.route('/expenses')
@login_required
def expenses():
    # Get current month and year for default filter
    current_date = datetime.now()
    current_month = f"{current_date.year}-{current_date.month:02d}"

    # Get unique buildings for filter from accessible units only
    accessible_units = get_accessible_units_query().filter(Unit.building.isnot(None)).all()

    # Extract unique building names from accessible units
    building_set = set()
    buildings = []
    for unit in accessible_units:
        if unit.building and unit.building.strip() and unit.building not in building_set:
            building_set.add(unit.building)
            buildings.append(unit.building)

    # Sort buildings alphabetically
    buildings.sort()

    return render_template('expenses.html', current_month=current_month, buildings=buildings)


# Replace the existing get_expenses() function with this updated version:
@expenses_bp.route('/api/expenses', methods=['GET'])
@login_required
def get_expenses():
    # Get query parameters
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    building = request.args.get('building', 'all')

    if not year or not month:
        return jsonify({'error': 'Year and month parameters are required'}), 400

    # Get accessible units for the current user
    units_query = get_accessible_units_query()

    # Apply building filter if specified
    if building != 'all':
        units_query = units_query.filter(Unit.building == building)

    units = units_query.all()

    # Format unit data for the response
    units_data = [{'id': unit.id, 'unit_number': unit.unit_number, 'building': unit.building} for unit in units]

    # Get expense data for the specified month and year, filtered by accessible units
    expenses_data = {}
    accessible_unit_ids = [unit.id for unit in units]

    if accessible_unit_ids:
        expenses = ExpenseData.query.filter(
            ExpenseData.company_id == current_user.company_id,
            ExpenseData.year == year,
            ExpenseData.month == month,
            ExpenseData.unit_id.in_(accessible_unit_ids)
        ).all()

        # Format expense data
        for expense in expenses:
            expenses_data[expense.unit_id] = {
                'sales': expense.sales,
                'rental': expense.rental,
                'electricity': expense.electricity,
                'water': expense.water,
                'sewage': expense.sewage,
                'internet': expense.internet,
                'cleaner': expense.cleaner,
                'laundry': expense.laundry,
                'supplies': expense.supplies,
                'repair': expense.repair,
                'replace': expense.replace,
                'other': expense.other
            }

    return jsonify({
        'units': units_data,
        'expenses': expenses_data
    })


# Replace the existing save_expenses() function with this updated version:
@expenses_bp.route('/api/expenses', methods=['POST'])
@login_required
def save_expenses():
    # Get data from request
    data = request.json

    if not data or 'year' not in data or 'month' not in data or 'expenses' not in data:
        return jsonify({'error': 'Invalid data format'}), 400

    year = data['year']
    month = data['month']
    expenses_data = data['expenses']
    company_id = current_user.company_id

    # Get accessible unit IDs for validation
    accessible_unit_ids = set(current_user.get_accessible_unit_ids())

    # Process each unit's expense data
    for unit_id, expense in expenses_data.items():
        # Convert unit_id to integer (it might be a string in JSON)
        unit_id = int(unit_id)

        # Check if user can access this unit
        if unit_id not in accessible_unit_ids:
            continue  # Skip if user doesn't have access to this unit

        # Check if unit belongs to the company (additional security check)
        unit = Unit.query.filter_by(id=unit_id, company_id=company_id).first()
        if not unit:
            continue  # Skip if unit doesn't belong to the company

        # Check if expense record already exists
        existing_expense = ExpenseData.query.filter_by(
            company_id=company_id,
            unit_id=unit_id,
            year=year,
            month=month
        ).first()

        if existing_expense:
            # Update existing record
            existing_expense.sales = expense.get('sales', '')
            existing_expense.rental = expense.get('rental', '')
            existing_expense.electricity = expense.get('electricity', '')
            existing_expense.water = expense.get('water', '')
            existing_expense.sewage = expense.get('sewage', '')
            existing_expense.internet = expense.get('internet', '')
            existing_expense.cleaner = expense.get('cleaner', '')
            existing_expense.laundry = expense.get('laundry', '')
            existing_expense.supplies = expense.get('supplies', '')
            existing_expense.repair = expense.get('repair', '')
            existing_expense.replace = expense.get('replace', '')
            existing_expense.other = expense.get('other', '')
        else:
            # Create new record
            new_expense = ExpenseData(
                company_id=company_id,
                unit_id=unit_id,
                year=year,
                month=month,
                sales=expense.get('sales', ''),
                rental=expense.get('rental', ''),
                electricity=expense.get('electricity', ''),
                water=expense.get('water', ''),
                sewage=expense.get('sewage', ''),
                internet=expense.get('internet', ''),
                cleaner=expense.get('cleaner', ''),
                laundry=expense.get('laundry', ''),
                supplies=expense.get('supplies', ''),
                repair=expense.get('repair', ''),
                replace=expense.get('replace', ''),
                other=expense.get('other', '')
            )
            db.session.add(new_expense)

    # Commit all changes
    db.session.commit()

    return jsonify({'success': True, 'message': 'Expenses data saved successfully'})


# Replace the existing get_monthly_revenue() function with this updated version:
@expenses_bp.route('/api/bookings/monthly_revenue')
@login_required
def get_monthly_revenue():
    # Get query parameters
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    if not year or not month:
        return jsonify({'error': 'Year and month parameters are required'}), 400

    # Get the company ID for the current user
    company_id = current_user.company_id

    # Get accessible unit IDs
    accessible_unit_ids = current_user.get_accessible_unit_ids()

    if not accessible_unit_ids:
        return jsonify({'revenues': {}})

    # Set date range for the specified month
    start_date = datetime(year, month, 1).date()
    if month == 12:
        end_date = datetime(year + 1, 1, 1).date()
    else:
        end_date = datetime(year, month + 1, 1).date()

    # Query bookings for the month, filtered by accessible units
    bookings = BookingForm.query.filter(
        BookingForm.company_id == company_id,
        BookingForm.unit_id.in_(accessible_unit_ids),
        (
            # Check-in during the month
                (BookingForm.check_in_date >= start_date) & (BookingForm.check_in_date < end_date) |
                # Check-out during the month
                (BookingForm.check_out_date > start_date) & (BookingForm.check_out_date <= end_date) |
                # Spanning the entire month
                (BookingForm.check_in_date <= start_date) & (BookingForm.check_out_date >= end_date)
        )
    ).all()

    # Calculate revenue per accessible unit
    revenues = {}
    for booking in bookings:
        unit_id = booking.unit_id
        if unit_id not in revenues:
            revenues[unit_id] = 0

        # Calculate the portion of booking revenue to attribute to this month
        total_nights = (booking.check_out_date - booking.check_in_date).days
        if total_nights <= 0:
            continue

        # Determine the nights that fall within the selected month
        night_start = max(booking.check_in_date, start_date)
        night_end = min(booking.check_out_date, end_date)
        nights_in_month = (night_end - night_start).days

        # Calculate prorated revenue for the month
        if total_nights > 0 and booking.price:
            try:
                daily_rate = float(booking.price) / total_nights
                month_revenue = daily_rate * nights_in_month
                revenues[unit_id] += month_revenue
            except (ValueError, TypeError):
                # Handle any conversion errors
                pass

    return jsonify({'revenues': revenues})


# Replace the existing get_monthly_issue_costs() function with this updated version:
@expenses_bp.route('/api/issues/monthly_costs')
@login_required
def get_monthly_issue_costs():
    # Get query parameters
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    issue_type = request.args.get('type')  # 'repair' or 'replace'

    if not year or not month:
        return jsonify({'error': 'Year and month parameters are required'}), 400

    # Get the company ID for the current user
    company_id = current_user.company_id

    # Get accessible unit IDs
    accessible_unit_ids = current_user.get_accessible_unit_ids()

    if not accessible_unit_ids:
        return jsonify({'costs': {}})

    # Set date range for the specified month
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)

    # Query to get issue costs for the month, filtered by accessible units
    query = Issue.query.filter(
        Issue.company_id == company_id,
        Issue.unit_id.in_(accessible_unit_ids),
        Issue.date_added >= start_date,
        Issue.date_added < end_date,
        Issue.cost.isnot(None)  # Only include issues with non-null cost
    )

    # Filter by type if specified
    if issue_type == 'repair':
        # Join with Type model to filter for "Repair" type
        repair_type = Type.query.filter_by(name='Repair').first()
        if repair_type:
            query = query.filter(Issue.type_id == repair_type.id)
    elif issue_type == 'replace':
        # Join with Type model to filter for "Replace" type
        replace_type = Type.query.filter_by(name='Replace').first()
        if replace_type:
            query = query.filter(Issue.type_id == replace_type.id)

    # Get the issues
    issues = query.all()

    # Calculate costs per accessible unit
    costs = {}
    for issue in issues:
        unit_id = issue.unit_id
        if unit_id not in costs:
            costs[unit_id] = 0

        try:
            if issue.cost:
                costs[unit_id] += float(issue.cost)
        except (ValueError, TypeError):
            # Handle any conversion errors
            pass

    return jsonify({'costs': costs})


# Replace the existing get_yearly_expenses() function with this updated version:
@expenses_bp.route('/api/expenses/yearly', methods=['GET'])
@login_required
def get_yearly_expenses():
    # Get query parameters
    year = request.args.get('year', type=int)
    building = request.args.get('building', 'all')

    if not year:
        return jsonify({'error': 'Year parameter is required'}), 400

    # Get the company ID for the current user
    company_id = current_user.company_id

    # Get accessible units for the company, filtered by building if specified
    units_query = get_accessible_units_query()
    if building != 'all':
        units_query = units_query.filter(Unit.building == building)

    units = units_query.all()

    # Format unit data for the response
    units_data = [{'id': unit.id, 'unit_number': unit.unit_number, 'building': unit.building} for unit in units]

    # Get expense data for all months in the specified year, filtered by accessible units
    yearly_expenses = {}
    accessible_unit_ids = [unit.id for unit in units]

    # For each accessible unit
    for unit in units:
        unit_id = unit.id
        yearly_expenses[unit_id] = {}

        # For each month
        for month in range(1, 13):
            # Check if we have data for this month
            expense_data = ExpenseData.query.filter_by(
                company_id=company_id,
                unit_id=unit_id,
                year=year,
                month=month
            ).first()

            if expense_data:
                # If we have data, format it
                yearly_expenses[unit_id][month] = {
                    'sales': float(expense_data.sales or 0),
                    'rental': float(expense_data.rental or 0),
                    'electricity': float(expense_data.electricity or 0),
                    'water': float(expense_data.water or 0),
                    'sewage': float(expense_data.sewage or 0),
                    'internet': float(expense_data.internet or 0),
                    'cleaner': float(expense_data.cleaner or 0),
                    'laundry': float(expense_data.laundry or 0),
                    'supplies': float(expense_data.supplies or 0),
                    'repair': float(expense_data.repair or 0),
                    'replace': float(expense_data.replace or 0),
                    'other': float(expense_data.other or 0)
                }
            else:
                # If we don't have data, use empty values
                yearly_expenses[unit_id][month] = {
                    'sales': 0,
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

    return jsonify({
        'units': units_data,
        'expenses': yearly_expenses
    })


# Replace the existing get_expense_years() function with this updated version:
@expenses_bp.route('/api/expenses/years', methods=['GET'])
@login_required
def get_expense_years():
    # Get the company ID for the current user
    company_id = current_user.company_id

    # Get accessible unit IDs
    accessible_unit_ids = current_user.get_accessible_unit_ids()

    if not accessible_unit_ids:
        # If no accessible units, return current year
        return jsonify({'years': [datetime.now().year]})

    # Get all years with expense data for accessible units
    years = db.session.query(ExpenseData.year) \
        .filter(
        ExpenseData.company_id == company_id,
        ExpenseData.unit_id.in_(accessible_unit_ids)
    ) \
        .distinct() \
        .order_by(ExpenseData.year.desc()) \
        .all()

    # Extract years from query result
    years_list = [year[0] for year in years]

    # If no years found, add current year
    if not years_list:
        years_list = [datetime.now().year]

    return jsonify({
        'years': years_list
    })


# Replace the existing get_expense_remarks() function with this updated version:
@expenses_bp.route('/api/expenses/remarks', methods=['GET'])
@login_required
def get_expense_remarks():
    # Get query parameters
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    if not year or not month:
        return jsonify({'error': 'Year and month parameters are required'}), 400

    # Get company ID
    company_id = current_user.company_id

    # Get accessible unit IDs
    accessible_unit_ids = current_user.get_accessible_unit_ids()

    if not accessible_unit_ids:
        return jsonify({'remarks': {}})

    # Query for remarks matching the criteria and accessible units
    remarks = ExpenseRemark.query.filter(
        ExpenseRemark.company_id == company_id,
        ExpenseRemark.year == year,
        ExpenseRemark.month == month,
        ExpenseRemark.unit_id.in_(accessible_unit_ids)
    ).all()

    # Format the remarks into the expected structure
    formatted_remarks = {}

    for remark in remarks:
        unit_id = remark.unit_id
        column_name = remark.column_name

        if unit_id not in formatted_remarks:
            formatted_remarks[unit_id] = {}

        formatted_remarks[unit_id][column_name] = remark.remark

    return jsonify({
        'remarks': formatted_remarks
    })


# Replace the existing save_expense_remarks() function with this updated version:
@expenses_bp.route('/api/expenses/remarks', methods=['POST'])
@login_required
def save_expense_remarks():
    # Get data from request
    data = request.json

    if not data or 'year' not in data or 'month' not in data or 'remarks' not in data:
        return jsonify({'error': 'Invalid data format'}), 400

    year = data['year']
    month = data['month']
    remarks_data = data['remarks']
    company_id = current_user.company_id

    # Get accessible unit IDs for validation
    accessible_unit_ids = set(current_user.get_accessible_unit_ids())

    # Process each unit's remarks
    for unit_id, columns in remarks_data.items():
        # Convert unit_id to integer (it might be a string in JSON)
        unit_id = int(unit_id)

        # Check if user can access this unit
        if unit_id not in accessible_unit_ids:
            continue  # Skip if user doesn't have access to this unit

        # Check if unit belongs to the company (additional security check)
        unit = Unit.query.filter_by(id=unit_id, company_id=company_id).first()
        if not unit:
            continue  # Skip if unit doesn't belong to the company

        # Process each column's remark
        for column_name, remark_text in columns.items():
            # Look for existing remark
            existing_remark = ExpenseRemark.query.filter_by(
                company_id=company_id,
                unit_id=unit_id,
                year=year,
                month=month,
                column_name=column_name
            ).first()

            if existing_remark:
                # Update existing remark
                existing_remark.remark = remark_text
                existing_remark.updated_at = datetime.utcnow()
            else:
                # Create new remark
                new_remark = ExpenseRemark(
                    company_id=company_id,
                    unit_id=unit_id,
                    year=year,
                    month=month,
                    column_name=column_name,
                    remark=remark_text
                )
                db.session.add(new_remark)

    # Commit changes
    try:
        db.session.commit()
        return jsonify({'success': True, 'message': 'Remarks saved successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500