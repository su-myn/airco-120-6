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
        sources = CalendarSource.query.filter_by(unit_id=unit.id, is_active=True).all()
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


@calendar_bp.route('/api/import_airbnb_csv', methods=['POST'])
@login_required
@permission_required('can_manage_bookings')
def import_airbnb_csv():
    # Get the bookings data from the request
    if not request.is_json:
        return jsonify({'success': False, 'message': 'Invalid request format. JSON expected.'}), 400

    data = request.json
    bookings = data.get('bookings', [])

    if not bookings:
        return jsonify({'success': False, 'message': 'No booking data provided.'}), 400

    # Get the user's company ID
    company_id = current_user.company_id

    # Counters for tracking what happened
    created_count = 0
    updated_count = 0
    error_count = 0

    for booking_data in bookings:
        try:
            # Check if confirmation code exists
            confirmation_code = booking_data.get('confirmation_code')
            if not confirmation_code:
                error_count += 1
                continue

            # Check if we already have this booking in our database
            existing_booking = BookingForm.query.filter_by(
                confirmation_code=confirmation_code,
                company_id=company_id
            ).first()

            # If booking exists, update it with new information
            if existing_booking:
                # Convert date strings to date objects
                try:
                    check_in_date = datetime.strptime(booking_data.get('check_in_date', ''), '%Y-%m-%d').date()
                    check_out_date = datetime.strptime(booking_data.get('check_out_date', ''), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    # Try different date format (like MM/DD/YYYY)
                    try:
                        check_in_date = datetime.strptime(booking_data.get('check_in_date', ''), '%m/%d/%Y').date()
                        check_out_date = datetime.strptime(booking_data.get('check_out_date', ''), '%m/%d/%Y').date()
                    except (ValueError, TypeError):
                        # Keep existing dates if parsing fails
                        check_in_date = existing_booking.check_in_date
                        check_out_date = existing_booking.check_out_date

                # Try to parse booking date
                booking_date = None
                # Update booking date if provided
                if booking_data.get('booking_date'):
                    parsed_date = parse_date(booking_data.get('booking_date'))
                    if parsed_date:
                        existing_booking.booking_date = parsed_date

                # Only update fields if they exist in the CSV
                if booking_data.get('guest_name'):
                    existing_booking.guest_name = booking_data.get('guest_name')
                if booking_data.get('contact_number'):
                    existing_booking.contact_number = booking_data.get('contact_number')

                # Update dates only if valid
                if check_in_date and check_out_date and check_in_date < check_out_date:
                    existing_booking.check_in_date = check_in_date
                    existing_booking.check_out_date = check_out_date
                    # Calculate nights from the dates
                    existing_booking.number_of_nights = (check_out_date - check_in_date).days

                # Update other fields
                if booking_data.get('price'):
                    try:
                        # Handle price as string, removing any non-numeric characters except periods
                        price_str = str(booking_data.get('price'))
                        # Remove any remaining 'RM' if it wasn't caught by JavaScript
                        price_str = price_str.replace('RM', '').replace(',', '').strip()
                        price_value = float(price_str)

                        if price_value > 0:
                            existing_booking.price = price_value
                    except (ValueError, TypeError) as e:
                        print(f"Failed to convert price: {booking_data.get('price')} - Error: {e}")

                if booking_data.get('payment_status'):
                    existing_booking.payment_status = booking_data.get('payment_status')

                # Update guest counts
                if 'adults' in booking_data and booking_data['adults'] > 0:
                    existing_booking.adults = booking_data['adults']
                if 'children' in booking_data and booking_data['children'] > 0:
                    existing_booking.children = booking_data['children']
                if 'infants' in booking_data and booking_data['infants'] > 0:
                    existing_booking.infants = booking_data['infants']

                # Update total number of guests
                existing_booking.number_of_guests = (
                        (existing_booking.adults or 0) +
                        (existing_booking.children or 0) +
                        (existing_booking.infants or 0)
                )

                updated_count += 1
            else:
                # This is a new booking - we would normally create it, but
                # in this case we'll skip it since we want to focus on updating existing bookings
                pass

        except Exception as e:
            error_count += 1
            print(f"Error processing booking: {e}")

    # Commit all changes
    db.session.commit()

    # Return the result
    return jsonify({
        'success': True,
        'message': f"Successfully processed {updated_count} bookings. Updated: {updated_count}, Errors: {error_count}",
        'updated': updated_count,
        'created': created_count,
        'errors': error_count
    })

# Helper function to process ICS calendars
def process_ics_calendar(calendar_data, unit_id, source, source_identifier=None):
    """Process ICS calendar data and handle bookings based on confirmation codes"""
    from icalendar import Calendar
    import re

    # Parse the ICS data
    try:
        cal = Calendar.from_ical(calendar_data)
    except Exception as e:
        print(f"Error parsing calendar: {str(e)}")
        return 0, 0, 0, []

    unit = Unit.query.get(unit_id)
    if not unit:
        return 0, 0, 0, []

    bookings_added = 0
    bookings_updated = 0
    bookings_cancelled = 0
    affected_booking_ids = []

    # Keep track of units affected for reporting
    affected_units = set()

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

    # Get existing bookings from database for this unit and source
    # FIXED: Only get bookings that were imported from THIS specific calendar source
    if source_identifier:
        # Try to find bookings that were imported from this specific source identifier
        # We'll use a special hidden field to track import source instead of notes
        existing_bookings = BookingForm.query.filter(
            BookingForm.unit_id == unit_id,
            BookingForm.booking_source == source,
            # We'll add logic to track import source differently
        ).all()

        # Filter bookings by checking if they have the same source pattern
        # This is a temporary solution - ideally use the mapping table approach
        filtered_bookings = []
        for booking in existing_bookings:
            # Check if this booking was likely imported from this source
            # by looking at timing and confirmation code patterns
            if should_manage_booking(booking, source, source_identifier):
                filtered_bookings.append(booking)
        existing_bookings = filtered_bookings

    else:
        # Fallback: Get all bookings for this source, but be more careful about cancellation
        existing_bookings = BookingForm.query.filter_by(
            unit_id=unit_id,
            booking_source=source
        ).all()

    # Check existing bookings against current calendar data
    existing_codes = set()
    updated_units = set()
    added_units = set()

    for booking in existing_bookings:
        if not booking.confirmation_code:
            continue

        existing_codes.add(booking.confirmation_code)

        if booking.confirmation_code in current_bookings:
            current_data = current_bookings[booking.confirmation_code]

            # Check if details need updating
            needs_update = (
                    booking.check_in_date != current_data['check_in_date'] or
                    booking.check_out_date != current_data['check_out_date'] or
                    booking.number_of_nights != current_data['number_of_nights']
            )

            if needs_update:
                # Update booking details
                booking.check_in_date = current_data['check_in_date']
                booking.check_out_date = current_data['check_out_date']
                booking.number_of_nights = current_data['number_of_nights']

                # DON'T update notes - leave them as they are for user input

                # Update guest name only if it's empty or was a generic import name
                if (not booking.guest_name or
                    booking.guest_name.startswith("Guest from") or
                    booking.guest_name == f"Guest from {source}") and current_data['guest_name']:
                    booking.guest_name = current_data['guest_name']

                bookings_updated += 1
                affected_booking_ids.append(booking.id)
                updated_units.add(unit.unit_number)
        else:
            # Only mark as cancelled if this booking was imported from THIS specific source
            should_cancel = should_cancel_booking(booking, source, source_identifier, existing_bookings)

            if should_cancel and booking.check_out_date >= datetime.utcnow().date():
                # Set cancellation status but DON'T modify user's notes
                booking.is_cancelled = True
                bookings_cancelled += 1
                affected_booking_ids.append(booking.id)

    # Add new bookings
    for confirmation_code, details in current_bookings.items():
        if confirmation_code not in existing_codes:
            new_booking = BookingForm(
                guest_name=details['guest_name'] or f"Guest from {source}",
                contact_number="",
                check_in_date=details['check_in_date'],
                check_out_date=details['check_out_date'],
                property_name=unit.building or "Property",
                unit_id=unit_id,
                number_of_nights=details['number_of_nights'],
                number_of_guests=2,  # Default value
                price=0,  # Default value
                booking_source=source,
                payment_status="Paid",
                notes="",  # LEAVE EMPTY for user input
                company_id=unit.company_id,
                user_id=current_user.id,
                confirmation_code=confirmation_code
            )

            db.session.add(new_booking)
            db.session.flush()
            bookings_added += 1
            affected_booking_ids.append(new_booking.id)
            added_units.add(unit.unit_number)

    # Commit all changes
    if bookings_added > 0 or bookings_updated > 0 or bookings_cancelled > 0:
        db.session.commit()

    return len(added_units), len(updated_units), bookings_cancelled, affected_booking_ids


def should_manage_booking(booking, source, source_identifier):
    """
    Determine if this booking should be managed by the current calendar source
    This is a helper function to avoid cross-contamination between different ICS imports
    """
    # For now, we'll use a simple heuristic based on creation time and source
    # In a more robust implementation, you'd use the mapping table approach

    # If the booking was created recently (within last import session),
    # and has the same source, it's likely from a recent import
    recent_threshold = datetime.utcnow() - timedelta(hours=24)

    if (booking.date_added > recent_threshold and
            booking.booking_source == source):
        return True

    # You could add more sophisticated logic here
    # For example, checking confirmation code patterns specific to different listing types

    return False


def should_cancel_booking(booking, source, source_identifier, all_existing_bookings):
    """
    Determine if a booking should be cancelled when it's not found in the current ICS
    """
    # Only cancel if we're confident this booking came from THIS specific source

    if source_identifier:
        # If we have a source identifier, only cancel bookings that we're managing
        return should_manage_booking(booking, source, source_identifier)
    else:
        # If no source identifier, be very conservative about cancelling
        # Only cancel if this is the only source for this platform
        other_active_sources = CalendarSource.query.filter(
            CalendarSource.unit_id == booking.unit_id,
            CalendarSource.source_name == source,
            CalendarSource.is_active == True
        ).count()

        # Only cancel if there's only one active source (this one)
        return other_active_sources <= 1

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


def parse_date(date_str):
    """Helper function to parse dates in various formats"""
    if not date_str or not date_str.strip():
        return None

    date_str = date_str.strip()

    # Try standard formats
    formats = [
        '%b %d, %Y',  # Jan 03, 2025
        '%B %d, %Y',  # January 03, 2025
        '%Y-%m-%d',  # 2025-01-03
        '%d/%m/%Y',  # 03/01/2025
        '%m/%d/%Y'  # 01/03/2025
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    # Try to handle formats with single-digit days (without leading zeros)
    # This is trickier in Python as strptime expects exact format matches

    # Parse month names manually
    month_names = {
        'jan': 1, 'january': 1,
        'feb': 2, 'february': 2,
        'mar': 3, 'march': 3,
        'apr': 4, 'april': 4,
        'may': 5, 'may': 5,
        'jun': 6, 'june': 6,
        'jul': 7, 'july': 7,
        'aug': 8, 'august': 8,
        'sep': 9, 'september': 9,
        'oct': 10, 'october': 10,
        'nov': 11, 'november': 11,
        'dec': 12, 'december': 12
    }

    # Check if it matches pattern like "Jan 3, 2025"
    import re
    match = re.match(r'([a-zA-Z]+)\s+(\d{1,2}),\s+(\d{4})', date_str)
    if match:
        month_name, day, year = match.groups()
        month_num = month_names.get(month_name.lower())
        if month_num:
            try:
                return datetime(int(year), month_num, int(day)).date()
            except ValueError:
                pass

    # If all attempts fail, return None
    print(f"Could not parse date: {date_str}")
    return None


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


# Updated process_ics_calendar function using the mapping table
def process_ics_calendar_with_mapping(calendar_data, unit_id, source, source_identifier=None):
    """Process ICS calendar data with proper source tracking"""
    from icalendar import Calendar
    import re

    # Parse the ICS data
    try:
        cal = Calendar.from_ical(calendar_data)
    except Exception as e:
        print(f"Error parsing calendar: {str(e)}")
        return 0, 0, 0, []

    unit = Unit.query.get(unit_id)
    if not unit:
        return 0, 0, 0, []

    # Get or create the calendar source
    calendar_source = CalendarSource.query.filter_by(
        unit_id=unit_id,
        source_name=source,
        source_identifier=source_identifier
    ).first()

    if not calendar_source:
        calendar_source = CalendarSource(
            unit_id=unit_id,
            source_name=source,
            source_identifier=source_identifier,
            is_active=True
        )
        db.session.add(calendar_source)
        db.session.flush()

    bookings_added = 0
    bookings_updated = 0
    bookings_cancelled = 0
    affected_booking_ids = []

    # Collect all confirmation codes from this specific ICS calendar
    current_bookings = {}

    for component in cal.walk():
        if component.name == "VEVENT":
            # Skip blocked dates or unavailable periods
            summary = str(component.get('summary', 'Booking'))
            if "blocked" in summary.lower() or "unavailable" in summary.lower():
                continue

            description = str(component.get('description', ''))
            confirmation_code = ""

            # Extract confirmation code based on platform
            if source == "Airbnb":
                url_match = re.search(r'reservations/details/([A-Z0-9]+)', description)
                if url_match:
                    confirmation_code = url_match.group(1)
            elif source == "Booking.com":
                booking_match = re.search(r'Booking ID:\s*(\d+)', description)
                if booking_match:
                    confirmation_code = booking_match.group(1)

            if not confirmation_code:
                continue

            # Process dates
            start_date = component.get('dtstart').dt
            end_date = component.get('dtend').dt

            if isinstance(start_date, datetime):
                start_date = start_date.date()
            if isinstance(end_date, datetime):
                end_date = end_date.date()

            nights = (end_date - start_date).days
            guest_name = extract_guest_name(summary, description)

            current_bookings[confirmation_code] = {
                'check_in_date': start_date,
                'check_out_date': end_date,
                'number_of_nights': nights,
                'guest_name': guest_name,
                'description': description
            }

    # Get existing bookings that were imported from THIS specific calendar source
    existing_booking_mappings = BookingCalendarSource.query.filter_by(
        calendar_source_id=calendar_source.id
    ).all()

    existing_bookings = {}
    for mapping in existing_booking_mappings:
        booking = mapping.booking
        if booking and booking.confirmation_code:
            existing_bookings[booking.confirmation_code] = booking

    # Process each booking from the current ICS
    current_codes = set(current_bookings.keys())
    existing_codes = set(existing_bookings.keys())

    # Update existing bookings
    for confirmation_code in existing_codes.intersection(current_codes):
        booking = existing_bookings[confirmation_code]
        current_data = current_bookings[confirmation_code]

        needs_update = (
            booking.check_in_date != current_data['check_in_date'] or
            booking.check_out_date != current_data['check_out_date'] or
            booking.number_of_nights != current_data['number_of_nights']
        )

        if needs_update:
            booking.check_in_date = current_data['check_in_date']
            booking.check_out_date = current_data['check_out_date']
            booking.number_of_nights = current_data['number_of_nights']

            new_note = f"Updated from {source}"
            if source_identifier:
                new_note += f" ({source_identifier})"
            new_note += f" on {datetime.utcnow().strftime('%Y-%m-%d')}"

            if booking.notes:
                booking.notes = f"{booking.notes}; {new_note}"
            else:
                booking.notes = new_note

            if (not booking.guest_name or booking.guest_name.startswith("Guest from")) and current_data['guest_name']:
                booking.guest_name = current_data['guest_name']

            bookings_updated += 1
            affected_booking_ids.append(booking.id)

    # Cancel bookings that are no longer in THIS calendar source
    for confirmation_code in existing_codes - current_codes:
        booking = existing_bookings[confirmation_code]
        if booking.check_out_date >= datetime.utcnow().date():
            cancel_note = f"Cancelled: No longer in {source}"
            if source_identifier:
                cancel_note += f" ({source_identifier})"
            cancel_note += f" as of {datetime.utcnow().strftime('%Y-%m-%d')}"

            if booking.notes:
                booking.notes = f"{booking.notes}; {cancel_note}"
            else:
                booking.notes = cancel_note

            booking.is_cancelled = True
            bookings_cancelled += 1
            affected_booking_ids.append(booking.id)

    # Add new bookings
    for confirmation_code in current_codes - existing_codes:
        details = current_bookings[confirmation_code]

        # Check if this confirmation code already exists from another source
        existing_booking = BookingForm.query.filter_by(
            confirmation_code=confirmation_code,
            unit_id=unit_id
        ).first()

        if existing_booking:
            # Create mapping to this calendar source as well
            existing_mapping = BookingCalendarSource.query.filter_by(
                booking_id=existing_booking.id,
                calendar_source_id=calendar_source.id
            ).first()

            if not existing_mapping:
                new_mapping = BookingCalendarSource(
                    booking_id=existing_booking.id,
                    calendar_source_id=calendar_source.id
                )
                db.session.add(new_mapping)
        else:
            # Create new booking
            new_booking = BookingForm(
                guest_name=details['guest_name'] or f"Guest from {source}",
                contact_number="",
                check_in_date=details['check_in_date'],
                check_out_date=details['check_out_date'],
                property_name=unit.building or "Property",
                unit_id=unit_id,
                number_of_nights=details['number_of_nights'],
                number_of_guests=2,
                price=0,
                booking_source=source,
                payment_status="Paid",
                notes=f"Imported from {source}" + (f" ({source_identifier})" if source_identifier else ""),
                company_id=unit.company_id,
                user_id=current_user.id,
                confirmation_code=confirmation_code
            )

            db.session.add(new_booking)
            db.session.flush()

            # Create mapping
            mapping = BookingCalendarSource(
                booking_id=new_booking.id,
                calendar_source_id=calendar_source.id
            )
            db.session.add(mapping)

            bookings_added += 1
            affected_booking_ids.append(new_booking.id)

    # Update calendar source timestamp
    calendar_source.last_updated = datetime.utcnow()

    # Commit all changes
    if bookings_added > 0 or bookings_updated > 0 or bookings_cancelled > 0:
        db.session.commit()

    return bookings_added, bookings_updated, bookings_cancelled, affected_booking_ids