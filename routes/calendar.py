from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from functools import wraps
from models import db, BookingForm, Unit, CalendarSource
import requests
import re
from utils.access_control import (
    get_accessible_units_query,
    get_accessible_bookings_query,
    check_unit_access
)
import os
import pytz

calendar_bp = Blueprint('calendar', __name__)

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

@calendar_bp.route('/calendar_view')
@login_required
@permission_required('can_view_bookings')
def calendar_view():
    # Get accessible units for this company for the filters
    units = get_accessible_units_query().all()

    return render_template('calendar_view.html', units=units)


@calendar_bp.route('/api/calendar/bookings')
@login_required
@permission_required('can_view_bookings')
def get_calendar_bookings():
    # Get accessible bookings for current user
    bookings = get_accessible_bookings_query().all()

    # Format the data for the calendar
    calendar_data = []
    for booking in bookings:
        calendar_data.append({
            'id': booking.id,
            'unit_id': booking.unit_id,
            'unit_number': booking.unit.unit_number,
            'building': booking.unit.building or '',  # Include building from Unit model
            'guest_name': booking.guest_name,
            'check_in_date': booking.check_in_date.isoformat(),
            'check_out_date': booking.check_out_date.isoformat(),
            'nights': booking.number_of_nights,
            'guests': booking.number_of_guests,
            'price': str(booking.price),
            'source': booking.booking_source,
            'payment_status': booking.payment_status,
            'contact': booking.contact_number
        })

    return jsonify(calendar_data)


@calendar_bp.route('/import_ics', methods=['GET', 'POST'])
@login_required
@permission_required('can_manage_bookings')
def import_ics():
    if request.method == 'POST':
        # Check if a unit was selected
        unit_id = request.form.get('unit_id')
        if not unit_id:
            flash('Please select a unit', 'danger')
            return redirect(url_for('calendar.import_ics'))

        # Check if user can access this unit
        if not check_unit_access(unit_id):
            flash('You do not have permission to import calendar for this unit', 'danger')
            return redirect(url_for('calendar.import_ics'))

        # Check if it's a URL import or file upload
        import_type = request.form.get('import_type')
        source = request.form.get('booking_source', 'Airbnb')
        source_identifier = request.form.get('source_identifier', '').strip()

        # If no custom identifier provided, create a default one
        if not source_identifier:
            # Count existing sources for this platform and unit
            existing_count = CalendarSource.query.filter_by(
                unit_id=unit_id,
                source_name=source
            ).count()
            source_identifier = f"{source} #{existing_count + 1}"

        calendar_data = None

        # Handle URL or file import (existing code)
        if import_type == 'url':
            ics_url = request.form.get('ics_url')
            if not ics_url:
                flash('Please enter an ICS URL', 'danger')
                return redirect(url_for('calendar.import_ics'))

            try:
                response = requests.get(ics_url)
                if response.status_code != 200:
                    flash(f'Error downloading ICS file: {response.status_code}', 'danger')
                    return redirect(url_for('calendar.import_ics'))

                calendar_data = response.text
            except Exception as e:
                flash(f'Error downloading ICS file: {str(e)}', 'danger')
                return redirect(url_for('calendar.import_ics'))

        elif import_type == 'file':
            if 'ics_file' not in request.files:
                flash('No file provided', 'danger')
                return redirect(url_for('calendar.import_ics'))

            file = request.files['ics_file']
            if file.filename == '':
                flash('No file selected', 'danger')
                return redirect(url_for('calendar.import_ics'))

            try:
                calendar_data = file.read().decode('utf-8')
            except UnicodeDecodeError:
                file.seek(0)
                calendar_data = file.read()
            except Exception as e:
                flash(f'Error reading file: {str(e)}', 'danger')
                return redirect(url_for('calendar.import_ics'))

        # Process the ICS data
        if calendar_data:
            try:
                units_added, units_updated, bookings_cancelled, affected_booking_ids = process_ics_calendar(
                    calendar_data, unit_id, source, source_identifier
                )

                # Update calendar source with the custom identifier
                source_url = request.form.get('ics_url') if import_type == 'url' else None
                update_calendar_source(unit_id, source, source_identifier, source_url)

                # Build success message
                message_parts = []
                if units_added > 0:
                    message_parts.append(f"{units_added} unit{'s' if units_added > 1 else ''} with new bookings")
                if units_updated > 0:
                    message_parts.append(f"{units_updated} unit{'s' if units_updated > 1 else ''} with updated bookings")
                if bookings_cancelled > 0:
                    message_parts.append(f"{bookings_cancelled} booking{'s' if bookings_cancelled > 1 else ''} marked as cancelled")

                if message_parts:
                    flash(f"Calendar '{source_identifier}' synchronized: {', '.join(message_parts)}", 'success')
                else:
                    flash(f"Calendar '{source_identifier}' synchronized: No changes detected", 'info')

                # Store affected booking IDs in session
                if affected_booking_ids:
                    session['highlight_booking_ids'] = affected_booking_ids

                # Redirect to bookings page
                if affected_booking_ids:
                    return redirect(url_for('bookings.bookings', highlight_ids=','.join(map(str, affected_booking_ids))))

            except Exception as e:
                flash(f'Error processing calendar: {str(e)}', 'danger')
                return redirect(url_for('calendar.import_ics'))

        return redirect(url_for('bookings.bookings'))

    # GET request - show the import form
    # Get accessible units for current user
    units = get_accessible_units_query().all()

    # Get existing calendar sources for accessible units only
    calendar_sources = {}
    for unit in units:
        sources = CalendarSource.query.filter_by(unit_id=unit.id).all()
        if sources:
            calendar_sources[unit.id] = sources

    return render_template('import_ics.html', units=units, calendar_sources=calendar_sources)


@calendar_bp.route('/refresh_calendar/<int:source_id>')
@login_required
@permission_required('can_manage_bookings')
def refresh_calendar(source_id):
    calendar_source = CalendarSource.query.get_or_404(source_id)

    # Check if user has access to this unit
    if calendar_source.unit.company_id != current_user.company_id:
        flash('You do not have permission to manage this calendar', 'danger')
        return redirect(url_for('calendar.import_ics'))

    # Check if user can access this specific unit
    if not check_unit_access(calendar_source.unit_id):
        flash('You do not have permission to manage this calendar', 'danger')
        return redirect(url_for('calendar.import_ics'))

    # Check if the source has a URL
    if not calendar_source.source_url:
        flash('This calendar source does not have a URL for refreshing', 'danger')
        return redirect(url_for('calendar.import_ics'))

    # Rest of the function remains the same...
    try:
        # Download the ICS file
        response = requests.get(calendar_source.source_url)
        if response.status_code != 200:
            flash(f'Error downloading ICS file: {response.status_code}', 'danger')
            return redirect(url_for('calendar.import_ics'))

        calendar_data = response.text

        # Process the calendar
        units_added, units_updated, bookings_cancelled, affected_booking_ids = process_ics_calendar(
            calendar_data,
            calendar_source.unit_id,
            calendar_source.source_name
        )

        # Update the last_updated timestamp
        calendar_source.last_updated = datetime.utcnow()
        db.session.commit()

        # Build message based on what actually happened
        message_parts = []
        if units_added > 0:
            message_parts.append(f"{units_added} unit{'s' if units_added > 1 else ''} with new bookings")
        if units_updated > 0:
            message_parts.append(f"{units_updated} unit{'s' if units_updated > 1 else ''} with updated bookings")
        if bookings_cancelled > 0:
            message_parts.append(f"{bookings_cancelled} booking{'s' if bookings_cancelled > 1 else ''} marked as cancelled")

        if message_parts:
            flash(f"Calendar synchronized: {', '.join(message_parts)}", 'success')
        else:
            flash(f"Calendar synchronized: No changes detected", 'info')

        # Store all affected booking IDs in the session
        if affected_booking_ids:
            session['highlight_booking_ids'] = affected_booking_ids
            return redirect(url_for('bookings.bookings', highlight_ids=','.join(map(str, affected_booking_ids))))

    except Exception as e:
        flash(f'Error refreshing calendar: {str(e)}', 'danger')

    return redirect(url_for('calendar.import_ics'))


@calendar_bp.route('/delete_calendar_source/<int:source_id>')
@login_required
@permission_required('can_manage_bookings')
def delete_calendar_source(source_id):
    calendar_source = CalendarSource.query.get_or_404(source_id)

    # Check if user has access to this unit
    if calendar_source.unit.company_id != current_user.company_id:
        flash('You do not have permission to manage this calendar', 'danger')
        return redirect(url_for('calendar.import_ics'))

    # Check if user can access this specific unit
    if not check_unit_access(calendar_source.unit_id):
        flash('You do not have permission to manage this calendar', 'danger')
        return redirect(url_for('calendar.import_ics'))

    # Delete the calendar source
    db.session.delete(calendar_source)
    db.session.commit()

    flash('Calendar source deleted successfully', 'success')
    return redirect(url_for('calendar.import_ics'))


# Helper function to process ICS calendars
def process_ics_calendar(calendar_data, unit_id, source, source_identifier=None, user=None):
    """Process ICS calendar data and handle bookings based on confirmation codes - FIXED VERSION"""
    from icalendar import Calendar
    import re
    from datetime import date

    # Parse the ICS data
    try:
        cal = Calendar.from_ical(calendar_data)
    except Exception as e:
        print(f"Error parsing calendar: {str(e)}")
        return 0, 0, 0, []

    # FIXED: Validate that the unit exists
    unit = Unit.query.get(unit_id)
    if not unit:
        print(f"Error: Unit with ID {unit_id} does not exist")
        return 0, 0, 0, []

    bookings_added = 0
    bookings_updated = 0
    bookings_cancelled = 0
    affected_booking_ids = []
    affected_units = set()

    # FIXED: Get today's date for filtering using Malaysia timezone
    today = datetime.now(pytz.timezone('Asia/Kuala_Lumpur')).date()

    # Collect all confirmation codes and their details from the ICS calendar
    current_bookings = {}

    for component in cal.walk():
        if component.name == "VEVENT":
            # Skip blocked dates or unavailable periods
            summary = str(component.get('summary', 'Booking'))
            if "blocked" in summary.lower() or "unavailable" in summary.lower():
                continue

            description = str(component.get('description', ''))

            # Extract confirmation code from the description field
            confirmation_code = ""

            # For Airbnb: Extract from URL like https://www.airbnb.com/hosting/reservations/details/HMN8ZKWAQE
            if source == "Airbnb":
                url_match = re.search(r'reservations/details/([A-Z0-9]+)', description)
                if url_match:
                    confirmation_code = url_match.group(1)

            # For other platforms - adapt as needed
            elif source == "Booking.com":
                booking_match = re.search(r'Booking ID:\s*(\d+)', description)
                if booking_match:
                    confirmation_code = booking_match.group(1)

            # If no valid confirmation code found, skip this entry
            if not confirmation_code:
                continue

            # Get start and end dates
            start_date = component.get('dtstart').dt
            end_date = component.get('dtend').dt

            # Convert datetime objects to date objects if needed
            if isinstance(start_date, datetime):
                start_date = start_date.date()
            if isinstance(end_date, datetime):
                end_date = end_date.date()

            # FILTER: Skip bookings with check-out date in the past (before today)
            if end_date < today:
                print(f"DEBUG: Skipping past booking {confirmation_code} with check-out date {end_date}")
                continue

            # Calculate number of nights
            nights = (end_date - start_date).days

            # Extract guest name from summary or description
            guest_name = extract_guest_name(summary, description)

            # Store booking details
            current_bookings[confirmation_code] = {
                'check_in_date': start_date,
                'check_out_date': end_date,
                'number_of_nights': nights,
                'guest_name': guest_name,
                'description': description,
                'source_identifier': source_identifier
            }

    print(f"DEBUG: Found {len(current_bookings)} valid future bookings in ICS with confirmation codes: {list(current_bookings.keys())}")

    # FIXED: Get existing bookings more intelligently - focus on confirmation codes
    current_codes = set(current_bookings.keys())

    if not current_codes:
        print("DEBUG: No valid future confirmation codes found in ICS, exiting")
        return 0, 0, 0, []

    # Query for existing bookings with ANY of the confirmation codes from this ICS
    existing_bookings_query = BookingForm.query.filter(
        BookingForm.unit_id == unit_id,
        BookingForm.confirmation_code.in_(list(current_codes))
    )

    # If we have source identifier, also filter by import source for more precision
    if source_identifier:
        existing_bookings_query = existing_bookings_query.filter(
            db.or_(
                BookingForm.import_source == source_identifier,
                BookingForm.import_source.is_(None)  # Include legacy bookings without import_source
            )
        )

    existing_bookings_with_codes = existing_bookings_query.all()

    # ADDITIONAL: Get ALL existing bookings for this unit/source to handle cancellations
    all_existing_bookings = BookingForm.query.filter(
        BookingForm.unit_id == unit_id,
        BookingForm.booking_source == source
    )

    if source_identifier:
        all_existing_bookings = all_existing_bookings.filter(
            db.or_(
                BookingForm.import_source == source_identifier,
                BookingForm.import_source.is_(None)
            )
        )

    all_existing_bookings = all_existing_bookings.all()

    # Create maps for easier lookup
    existing_codes = set()
    existing_booking_map = {}

    # Map by confirmation code (most reliable)
    for booking in existing_bookings_with_codes:
        if booking.confirmation_code and booking.confirmation_code.strip():
            existing_codes.add(booking.confirmation_code)
            existing_booking_map[booking.confirmation_code] = booking

    print(f"DEBUG: Found {len(existing_codes)} existing bookings with confirmation codes: {list(existing_codes)}")

    # FIXED: Process updates for existing bookings (by confirmation code)
    for confirmation_code in existing_codes.intersection(current_codes):
        booking = existing_booking_map[confirmation_code]
        current_data = current_bookings[confirmation_code]

        needs_update = (
                booking.check_in_date != current_data['check_in_date'] or
                booking.check_out_date != current_data['check_out_date'] or
                booking.number_of_nights != current_data['number_of_nights']
        )

        if needs_update:
            print(f"DEBUG: Updating booking {confirmation_code}")
            # Update booking details
            booking.check_in_date = current_data['check_in_date']
            booking.check_out_date = current_data['check_out_date']
            booking.number_of_nights = current_data['number_of_nights']

            # Update guest name only if it's better than what we have
            if (not booking.guest_name or
                booking.guest_name.startswith("Guest from") or
                booking.guest_name == f"Guest from {source}") and current_data['guest_name']:
                booking.guest_name = current_data['guest_name']

            # Update import source tracking
            booking.import_source = source_identifier or source
            booking.import_timestamp = datetime.utcnow()

            bookings_updated += 1
            affected_booking_ids.append(booking.id)
            affected_units.add(unit.unit_number)

    # FIXED: Add new bookings (check for duplicates more thoroughly)
    for confirmation_code in current_codes - existing_codes:
        details = current_bookings[confirmation_code]

        # ADDITIONAL CHECK: Before creating, check if a booking with this confirmation code
        # already exists anywhere in the system (to prevent duplicates across different syncs)
        duplicate_check = BookingForm.query.filter(
            BookingForm.confirmation_code == confirmation_code,
            BookingForm.company_id == unit.company_id  # Same company
        ).first()

        if duplicate_check:
            print(f"DEBUG: Skipping duplicate booking {confirmation_code} - already exists with ID {duplicate_check.id}")
            continue

        print(f"DEBUG: Adding new booking {confirmation_code}")

        # Determine user_id to use
        if user:
            user_id_to_use = user.id
        else:
            # Use current_user if available, otherwise fallback to a default
            try:
                user_id_to_use = current_user.id
            except:
                # If current_user is not available (scheduled context), find an admin user
                from models import User
                admin_user = User.query.filter_by(
                    company_id=unit.company_id,
                    is_admin=True
                ).first()
                if admin_user:
                    user_id_to_use = admin_user.id
                else:
                    # Fallback to any user from this company
                    any_user = User.query.filter_by(company_id=unit.company_id).first()
                    user_id_to_use = any_user.id if any_user else 1

        # Create new booking
        new_booking = BookingForm(
            guest_name=details['guest_name'] or f"Guest from {source}",
            contact_number="",  # ICS doesn't usually have this
            check_in_date=details['check_in_date'],
            check_out_date=details['check_out_date'],
            property_name=unit.building or "Property",
            unit_id=unit_id,
            number_of_nights=details['number_of_nights'],
            number_of_guests=2,  # Default value
            price=0,  # Default value - can be updated manually
            booking_source=source,
            payment_status="Paid",  # Assume paid for imported bookings
            notes="",
            company_id=unit.company_id,
            user_id=user_id_to_use,
            confirmation_code=confirmation_code,
            # Track import source
            import_source=source_identifier or source,
            import_timestamp=datetime.utcnow()
        )

        db.session.add(new_booking)
        db.session.flush()  # Get the ID
        bookings_added += 1
        affected_booking_ids.append(new_booking.id)
        affected_units.add(unit.unit_number)

    # CRITICAL FIX: Handle cancelled bookings more carefully - DON'T CANCEL PAST BOOKINGS
    # Get today's date in Malaysia timezone (define once for the loop)
    today_malaysia = datetime.now(pytz.timezone('Asia/Kuala_Lumpur')).date()

    for booking in all_existing_bookings:
        if not booking.confirmation_code:
            continue

        # CRITICAL FIX: Never cancel bookings that have already checked out (past bookings)
        # Past bookings are historical data and should be preserved even if no longer in ICS
        if booking.check_out_date < today_malaysia:
            print(f"DEBUG: Skipping cancellation of past booking {booking.confirmation_code} - already checked out on {booking.check_out_date}")
            continue

        # If this booking's confirmation code is not in current ICS (and it's a future booking)
        if booking.confirmation_code not in current_codes:
            # Only cancel if this booking was imported by THIS specific source
            should_cancel = False

            if source_identifier:
                # If we have a source identifier, only cancel if it matches
                should_cancel = (booking.import_source == source_identifier)
            else:
                # If no source identifier, be more conservative
                # Only cancel if this is the only active source for this platform
                other_sources = CalendarSource.query.filter(
                    CalendarSource.unit_id == unit_id,
                    CalendarSource.source_name == source,
                    CalendarSource.is_active == True
                ).count()

                should_cancel = (other_sources <= 1)

            # Additional check: Only cancel future bookings (double-check) and not already cancelled
            if should_cancel and booking.check_out_date >= today_malaysia and not booking.is_cancelled:
                print(f"DEBUG: Marking future booking {booking.confirmation_code} as cancelled")
                booking.is_cancelled = True

                # Add note about cancellation
                cancel_note = f"Auto-cancelled: No longer in {source}"
                if source_identifier:
                    cancel_note += f" ({source_identifier})"
                cancel_note += f" as of {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"

                if booking.notes:
                    booking.notes = f"{booking.notes}; {cancel_note}"
                else:
                    booking.notes = cancel_note

                bookings_cancelled += 1
                affected_booking_ids.append(booking.id)

    # Commit all changes
    if bookings_added > 0 or bookings_updated > 0 or bookings_cancelled > 0:
        try:
            db.session.commit()
            print(f"DEBUG: Successfully committed {bookings_added} new, {bookings_updated} updated, {bookings_cancelled} cancelled bookings")
        except Exception as e:
            print(f"ERROR: Failed to commit changes: {str(e)}")
            db.session.rollback()
            return 0, 0, 0, []

    return len(affected_units), len(affected_units), bookings_cancelled, affected_booking_ids


def process_ics_calendar_scheduled(calendar_data, unit_id, source, source_identifier=None, user_id=None):
    """Process ICS calendar data for scheduled jobs (without request context) - FIXED VERSION"""
    from icalendar import Calendar
    import re
    from datetime import date

    # Parse the ICS data
    try:
        cal = Calendar.from_ical(calendar_data)
    except Exception as e:
        print(f"Error parsing calendar: {str(e)}")
        return 0, 0, 0, []

    # FIXED: Validate that the unit exists
    unit = Unit.query.get(unit_id)
    if not unit:
        print(f"Error: Unit with ID {unit_id} does not exist")
        return 0, 0, 0, []

    bookings_added = 0
    bookings_updated = 0
    bookings_cancelled = 0
    affected_booking_ids = []

    # Keep track of units affected for reporting
    affected_units = set()

    # FIXED: Get today's date for filtering using Malaysia timezone
    today = datetime.now(pytz.timezone('Asia/Kuala_Lumpur')).date()

    # Collect all confirmation codes and their details from the ICS calendar
    current_bookings = {}

    for component in cal.walk():
        if component.name == "VEVENT":
            # Skip blocked dates or unavailable periods
            summary = str(component.get('summary', 'Booking'))
            if "blocked" in summary.lower() or "unavailable" in summary.lower():
                continue

            description = str(component.get('description', ''))

            # Extract confirmation code from the description field
            confirmation_code = ""

            # For Airbnb: Extract from URL like https://www.airbnb.com/hosting/reservations/details/HMN8ZKWAQE
            if source == "Airbnb":
                url_match = re.search(r'reservations/details/([A-Z0-9]+)', description)
                if url_match:
                    confirmation_code = url_match.group(1)

            # For other platforms - adapt as needed
            elif source == "Booking.com":
                booking_match = re.search(r'Booking ID:\s*(\d+)', description)
                if booking_match:
                    confirmation_code = booking_match.group(1)

            # If no valid confirmation code found, skip this entry
            if not confirmation_code:
                continue

            # Get start and end dates
            start_date = component.get('dtstart').dt
            end_date = component.get('dtend').dt

            # Convert datetime objects to date objects if needed
            if isinstance(start_date, datetime):
                start_date = start_date.date()
            if isinstance(end_date, datetime):
                end_date = end_date.date()

            # FILTER: Skip bookings with check-out date in the past (before today)
            if end_date < today:
                print(f"DEBUG: Skipping past booking {confirmation_code} with check-out date {end_date}")
                continue

            # Calculate number of nights
            nights = (end_date - start_date).days

            # Extract guest name from summary or description
            guest_name = extract_guest_name(summary, description)

            # Store booking details
            current_bookings[confirmation_code] = {
                'check_in_date': start_date,
                'check_out_date': end_date,
                'number_of_nights': nights,
                'guest_name': guest_name,
                'description': description,
                'source_identifier': source_identifier
            }

    # Get existing bookings for this source
    if source_identifier:
        existing_bookings = BookingForm.query.filter(
            BookingForm.unit_id == unit_id,
            BookingForm.booking_source == source,
            BookingForm.import_source == source_identifier
        ).all()
    else:
        existing_bookings = BookingForm.query.filter(
            BookingForm.unit_id == unit_id,
            BookingForm.booking_source == source
        ).all()

    # Create sets for easier comparison
    current_codes = set(current_bookings.keys())
    existing_codes = set()
    existing_booking_map = {}

    # Build map of existing bookings by confirmation code
    for booking in existing_bookings:
        if booking.confirmation_code:
            existing_codes.add(booking.confirmation_code)
            existing_booking_map[booking.confirmation_code] = booking

    print(f"DEBUG: Found {len(current_codes)} bookings in ICS")
    print(f"DEBUG: Found {len(existing_codes)} existing bookings in database")

    # Process updates for existing bookings
    for confirmation_code in existing_codes.intersection(current_codes):
        booking = existing_booking_map[confirmation_code]
        current_data = current_bookings[confirmation_code]

        needs_update = (
                booking.check_in_date != current_data['check_in_date'] or
                booking.check_out_date != current_data['check_out_date'] or
                booking.number_of_nights != current_data['number_of_nights']
        )

        if needs_update:
            print(f"DEBUG: Updating booking {confirmation_code}")
            # Update booking details
            booking.check_in_date = current_data['check_in_date']
            booking.check_out_date = current_data['check_out_date']
            booking.number_of_nights = current_data['number_of_nights']

            # Update guest name only if it's better than what we have
            if (not booking.guest_name or
                booking.guest_name.startswith("Guest from") or
                booking.guest_name == f"Guest from {source}") and current_data['guest_name']:
                booking.guest_name = current_data['guest_name']

            # Update import source tracking
            booking.import_source = source_identifier or source
            booking.import_timestamp = datetime.utcnow()

            bookings_updated += 1
            affected_booking_ids.append(booking.id)
            affected_units.add(unit.unit_number)

    # Add new bookings
    for confirmation_code in current_codes - existing_codes:
        details = current_bookings[confirmation_code]

        print(f"DEBUG: Adding new booking {confirmation_code}")

        # Create new booking
        new_booking = BookingForm(
            guest_name=details['guest_name'] or f"Guest from {source}",
            contact_number="",  # ICS doesn't usually have this
            check_in_date=details['check_in_date'],
            check_out_date=details['check_out_date'],
            property_name=unit.building or "Property",
            unit_id=unit_id,
            number_of_nights=details['number_of_nights'],
            number_of_guests=2,  # Default value
            price=0,  # Default value - can be updated manually
            booking_source=source,
            payment_status="Paid",  # Assume paid for imported bookings
            notes="",
            company_id=unit.company_id,
            user_id=user_id,  # Use the passed user_id instead of current_user.id
            confirmation_code=confirmation_code,
            # Track import source
            import_source=source_identifier or source,
            import_timestamp=datetime.utcnow()
        )

        db.session.add(new_booking)
        db.session.flush()  # Get the ID
        bookings_added += 1
        affected_booking_ids.append(new_booking.id)
        affected_units.add(unit.unit_number)

    # CRITICAL FIX: Handle cancelled bookings more carefully - DON'T CANCEL PAST BOOKINGS
    # Get today's date in Malaysia timezone (define once for the loop)
    today_malaysia = datetime.now(pytz.timezone('Asia/Kuala_Lumpur')).date()

    for confirmation_code in existing_codes - current_codes:
        booking = existing_booking_map[confirmation_code]

        # CRITICAL FIX: Never cancel bookings that have already checked out (past bookings)
        # Past bookings are historical data and should be preserved even if no longer in ICS
        if booking.check_out_date < today_malaysia:
            print(f"DEBUG: Skipping cancellation of past booking {confirmation_code} - already checked out on {booking.check_out_date}")
            continue

        # Only cancel if this booking was imported from this specific source
        should_cancel = False

        if source_identifier:
            should_cancel = (booking.import_source == source_identifier)
        else:
            other_sources = CalendarSource.query.filter(
                CalendarSource.unit_id == unit_id,
                CalendarSource.source_name == source,
                CalendarSource.is_active == True,
                CalendarSource.id != (CalendarSource.query.filter_by(
                    unit_id=unit_id,
                    source_name=source,
                    source_identifier=source_identifier
                ).first().id if source_identifier else None)
            ).count()

            should_cancel = (other_sources == 0)

        # Additional check: Only cancel future bookings (double-check) and not already cancelled
        if should_cancel and booking.check_out_date >= today_malaysia and not booking.is_cancelled:
            print(f"DEBUG: Marking future booking {confirmation_code} as cancelled")
            booking.is_cancelled = True

            # Add note about cancellation
            cancel_note = f"Auto-cancelled: No longer in {source}"
            if source_identifier:
                cancel_note += f" ({source_identifier})"
            cancel_note += f" as of {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"

            if booking.notes:
                booking.notes = f"{booking.notes}; {cancel_note}"
            else:
                booking.notes = cancel_note

            bookings_cancelled += 1
            affected_booking_ids.append(booking.id)

    # Commit all changes
    if bookings_added > 0 or bookings_updated > 0 or bookings_cancelled > 0:
        try:
            db.session.commit()
            print(f"DEBUG: Successfully committed {bookings_added} new, {bookings_updated} updated, {bookings_cancelled} cancelled bookings")
        except Exception as e:
            print(f"ERROR: Failed to commit changes: {str(e)}")
            db.session.rollback()
            return 0, 0, 0, []

    return len(affected_units), len(affected_units), bookings_cancelled, affected_booking_ids


def extract_guest_name(summary, description):
    """Extract guest name from summary or description"""
    # Different platforms use different formats for guest information
    import re

    # Try various patterns
    patterns = [
        r"(?:Booking for|Guest:|Reserved by|Reservation for)\s+([A-Za-z\s]+)",
        r"([A-Za-z\s]+)'s reservation"
    ]

    for pattern in patterns:
        # Search in summary
        match = re.search(pattern, summary)
        if match:
            return match.group(1).strip()

        # Search in description
        match = re.search(pattern, description)
        if match:
            return match.group(1).strip()

    # If no pattern matches, try to use the summary as is
    if summary and len(summary) < 50 and not any(x in summary.lower() for x in ["booking", "reservation", "blocked"]):
        return summary

    return None


def update_calendar_source(unit_id, source_name, source_identifier, source_url=None):
    """Update or create a calendar source record with unique identifier"""

    # Look for existing source by URL if provided, otherwise by identifier
    calendar_source = None

    if source_url:
        # Check if we already have this URL
        calendar_source = CalendarSource.query.filter_by(
            unit_id=unit_id,
            source_url=source_url
        ).first()

    if not calendar_source:
        # Check by source_name and identifier combination
        calendar_source = CalendarSource.query.filter_by(
            unit_id=unit_id,
            source_name=source_name,
            source_identifier=source_identifier
        ).first()

    if calendar_source:
        # Update existing record
        calendar_source.last_updated = datetime.utcnow()
        calendar_source.is_active = True
        if source_url:
            calendar_source.source_url = source_url
    else:
        # Create new record
        calendar_source = CalendarSource(
            unit_id=unit_id,
            source_name=source_name,
            source_identifier=source_identifier,
            source_url=source_url,
            last_updated=datetime.utcnow(),
            is_active=True
        )
        db.session.add(calendar_source)

    db.session.commit()
    return calendar_source


@calendar_bp.route('/toggle_source/<int:source_id>/<action>')
@login_required
@permission_required('can_manage_bookings')
def toggle_calendar_source(source_id, action):
    calendar_source = CalendarSource.query.get_or_404(source_id)

    # Check if user has access to this unit
    if calendar_source.unit.company_id != current_user.company_id:
        flash('You do not have permission to manage this calendar', 'danger')
        return redirect(url_for('calendar.import_ics'))

    # Check if user can access this specific unit
    if not check_unit_access(calendar_source.unit_id):
        flash('You do not have permission to manage this calendar', 'danger')
        return redirect(url_for('calendar.import_ics'))

    # Toggle the active status
    if action == 'enable':
        calendar_source.is_active = True
        flash(f'Calendar source "{calendar_source.source_identifier}" enabled successfully', 'success')
    elif action == 'disable':
        calendar_source.is_active = False
        flash(f'Calendar source "{calendar_source.source_identifier}" disabled successfully', 'info')
    else:
        flash('Invalid action', 'danger')
        return redirect(url_for('calendar.import_ics'))

    db.session.commit()
    return redirect(url_for('calendar.import_ics'))


@calendar_bp.route('/refresh_all_calendars')
@login_required
@permission_required('can_manage_bookings')
def refresh_all_calendars():
    """Refresh all active calendar sources for the current user's accessible units"""

    # Get accessible units for this user
    accessible_unit_ids = current_user.get_accessible_unit_ids()

    if not accessible_unit_ids:
        flash('You do not have access to any units', 'danger')
        return redirect(url_for('bookings.bookings'))

    # Get all active calendar sources for accessible units that have URLs
    calendar_sources = CalendarSource.query.filter(
        CalendarSource.unit_id.in_(accessible_unit_ids),
        CalendarSource.source_url.isnot(None),
        CalendarSource.source_url != '',
        CalendarSource.is_active == True
    ).all()

    if not calendar_sources:
        flash('No active calendar sources found to refresh', 'info')
        return redirect(url_for('bookings.bookings'))

    # Track results
    total_sources = len(calendar_sources)
    successful_refreshes = 0
    failed_refreshes = 0
    total_bookings_added = 0
    total_bookings_updated = 0
    total_bookings_cancelled = 0
    all_affected_booking_ids = []

    print(f"Starting bulk refresh of {total_sources} calendar sources...")

    for source in calendar_sources:
        try:
            print(
                f"Refreshing calendar: {source.source_identifier or source.source_name} for unit {source.unit.unit_number}")

            # Download the ICS file
            headers = {
                'User-Agent': 'PropertyHub Calendar Sync/1.0',
                'Accept': 'text/calendar,application/calendar,text/plain,*/*'
            }

            response = requests.get(
                source.source_url,
                timeout=30,
                headers=headers,
                allow_redirects=True
            )

            if response.status_code == 200:
                calendar_data = response.text

                # Process the calendar using the existing function
                units_added, units_updated, bookings_cancelled, affected_booking_ids = process_ics_calendar(
                    calendar_data,
                    source.unit_id,
                    source.source_name,
                    source.source_identifier or source.source_name
                )

                # Update the last_updated timestamp
                source.last_updated = datetime.utcnow()

                # Track totals
                total_bookings_added += units_added
                total_bookings_updated += units_updated
                total_bookings_cancelled += bookings_cancelled
                all_affected_booking_ids.extend(affected_booking_ids)

                successful_refreshes += 1
                print(f"✓ Successfully refreshed {source.source_identifier or source.source_name}")

            else:
                print(f"✗ HTTP {response.status_code} for {source.source_identifier or source.source_name}")
                failed_refreshes += 1

        except requests.exceptions.Timeout:
            print(f"✗ Timeout refreshing {source.source_identifier or source.source_name}")
            failed_refreshes += 1

        except Exception as e:
            print(f"✗ Error refreshing {source.source_identifier or source.source_name}: {str(e)}")
            failed_refreshes += 1

    # Commit all changes
    try:
        db.session.commit()
        print(f"✓ Successfully committed all calendar refresh changes")
    except Exception as e:
        print(f"✗ Error committing changes: {str(e)}")
        db.session.rollback()

    # Build success message
    message_parts = []
    if total_bookings_added > 0:
        message_parts.append(f"{total_bookings_added} new booking{'s' if total_bookings_added > 1 else ''}")
    if total_bookings_updated > 0:
        message_parts.append(f"{total_bookings_updated} updated booking{'s' if total_bookings_updated > 1 else ''}")
    if total_bookings_cancelled > 0:
        message_parts.append(
            f"{total_bookings_cancelled} cancelled booking{'s' if total_bookings_cancelled > 1 else ''}")

    # Create final message
    if successful_refreshes > 0 and failed_refreshes == 0:
        if message_parts:
            flash(f"Successfully refreshed all {successful_refreshes} calendar sources: {', '.join(message_parts)}",
                  'success')
        else:
            flash(f"Successfully refreshed all {successful_refreshes} calendar sources: No changes detected", 'info')
    elif successful_refreshes > 0 and failed_refreshes > 0:
        base_message = f"Refreshed {successful_refreshes} of {total_sources} calendar sources"
        if message_parts:
            base_message += f": {', '.join(message_parts)}"
        base_message += f". {failed_refreshes} source{'s' if failed_refreshes > 1 else ''} failed to refresh."
        flash(base_message, 'warning')
    else:
        flash(f"Failed to refresh all {total_sources} calendar sources. Please try again or check individual sources.",
              'danger')

    # Store affected booking IDs in session for highlighting
    if all_affected_booking_ids:
        # Remove duplicates while preserving order
        unique_ids = []
        seen = set()
        for booking_id in all_affected_booking_ids:
            if booking_id not in seen:
                unique_ids.append(booking_id)
                seen.add(booking_id)

        session['highlight_booking_ids'] = unique_ids
        return redirect(url_for('bookings.bookings', highlight_ids=','.join(map(str, unique_ids))))

    return redirect(url_for('bookings.bookings'))


# Add this additional API route to calendar.py for AJAX-based refresh

@calendar_bp.route('/api/refresh_all_calendars', methods=['POST'])
@login_required
@permission_required('can_manage_bookings')
def api_refresh_all_calendars():
    """API endpoint to refresh all active calendar sources via AJAX"""

    try:
        # Get accessible units for this user
        accessible_unit_ids = current_user.get_accessible_unit_ids()

        if not accessible_unit_ids:
            return jsonify({
                'success': False,
                'message': 'You do not have access to any units'
            }), 403

        # Get all active calendar sources for accessible units that have URLs
        calendar_sources = CalendarSource.query.filter(
            CalendarSource.unit_id.in_(accessible_unit_ids),
            CalendarSource.source_url.isnot(None),
            CalendarSource.source_url != '',
            CalendarSource.is_active == True
        ).all()

        if not calendar_sources:
            return jsonify({
                'success': True,
                'message': 'No active calendar sources found to refresh',
                'total_sources': 0,
                'successful': 0,
                'failed': 0,
                'results': []
            })

        # Track results
        total_sources = len(calendar_sources)
        successful_refreshes = 0
        failed_refreshes = 0
        total_bookings_added = 0
        total_bookings_updated = 0
        total_bookings_cancelled = 0
        all_affected_booking_ids = []
        detailed_results = []

        print(f"API: Starting bulk refresh of {total_sources} calendar sources...")

        for source in calendar_sources:
            source_result = {
                'source_id': source.id,
                'unit_number': source.unit.unit_number,
                'source_name': source.source_name,
                'source_identifier': source.source_identifier or source.source_name,
                'success': False,
                'error': None,
                'added': 0,
                'updated': 0,
                'cancelled': 0
            }

            try:
                print(
                    f"API: Refreshing {source.source_identifier or source.source_name} for unit {source.unit.unit_number}")

                # Download the ICS file
                headers = {
                    'User-Agent': 'PropertyHub Calendar Sync/1.0',
                    'Accept': 'text/calendar,application/calendar,text/plain,*/*'
                }

                response = requests.get(
                    source.source_url,
                    timeout=30,
                    headers=headers,
                    allow_redirects=True
                )

                if response.status_code == 200:
                    calendar_data = response.text

                    # Process the calendar using the existing function
                    units_added, units_updated, bookings_cancelled, affected_booking_ids = process_ics_calendar(
                        calendar_data,
                        source.unit_id,
                        source.source_name,
                        source.source_identifier or source.source_name
                    )

                    # Update the last_updated timestamp
                    source.last_updated = datetime.utcnow()

                    # Update source result
                    source_result.update({
                        'success': True,
                        'added': units_added,
                        'updated': units_updated,
                        'cancelled': bookings_cancelled
                    })

                    # Track totals
                    total_bookings_added += units_added
                    total_bookings_updated += units_updated
                    total_bookings_cancelled += bookings_cancelled
                    all_affected_booking_ids.extend(affected_booking_ids)

                    successful_refreshes += 1
                    print(f"API: ✓ Successfully refreshed {source.source_identifier or source.source_name}")

                else:
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    source_result['error'] = error_msg
                    print(f"API: ✗ {error_msg} for {source.source_identifier or source.source_name}")
                    failed_refreshes += 1

            except requests.exceptions.Timeout:
                error_msg = "Request timeout (30s)"
                source_result['error'] = error_msg
                print(f"API: ✗ Timeout for {source.source_identifier or source.source_name}")
                failed_refreshes += 1

            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                source_result['error'] = error_msg
                print(f"API: ✗ Error for {source.source_identifier or source.source_name}: {error_msg}")
                failed_refreshes += 1

            detailed_results.append(source_result)

        # Commit all changes
        try:
            db.session.commit()
            print(f"API: ✓ Successfully committed all calendar refresh changes")
        except Exception as e:
            print(f"API: ✗ Error committing changes: {str(e)}")
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': f'Database error: {str(e)}'
            }), 500

        # Build response message
        message_parts = []
        if total_bookings_added > 0:
            message_parts.append(f"{total_bookings_added} new booking{'s' if total_bookings_added > 1 else ''}")
        if total_bookings_updated > 0:
            message_parts.append(f"{total_bookings_updated} updated booking{'s' if total_bookings_updated > 1 else ''}")
        if total_bookings_cancelled > 0:
            message_parts.append(
                f"{total_bookings_cancelled} cancelled booking{'s' if total_bookings_cancelled > 1 else ''}")

        # Create final message
        if successful_refreshes > 0 and failed_refreshes == 0:
            if message_parts:
                message = f"Successfully refreshed all {successful_refreshes} calendar sources: {', '.join(message_parts)}"
            else:
                message = f"Successfully refreshed all {successful_refreshes} calendar sources: No changes detected"
        elif successful_refreshes > 0 and failed_refreshes > 0:
            base_message = f"Refreshed {successful_refreshes} of {total_sources} calendar sources"
            if message_parts:
                base_message += f": {', '.join(message_parts)}"
            base_message += f". {failed_refreshes} source{'s' if failed_refreshes > 1 else ''} failed."
            message = base_message
        else:
            message = f"Failed to refresh all {total_sources} calendar sources. Please check individual sources."

        # Store affected booking IDs in session for highlighting
        if all_affected_booking_ids:
            # Remove duplicates while preserving order
            unique_ids = []
            seen = set()
            for booking_id in all_affected_booking_ids:
                if booking_id not in seen:
                    unique_ids.append(booking_id)
                    seen.add(booking_id)

            session['highlight_booking_ids'] = unique_ids

        return jsonify({
            'success': failed_refreshes == 0,
            'message': message,
            'total_sources': total_sources,
            'successful': successful_refreshes,
            'failed': failed_refreshes,
            'total_added': total_bookings_added,
            'total_updated': total_bookings_updated,
            'total_cancelled': total_bookings_cancelled,
            'affected_booking_ids': all_affected_booking_ids,
            'results': detailed_results
        })

    except Exception as e:
        print(f"API: Critical error in refresh_all_calendars: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Unexpected error: {str(e)}'
        }), 500