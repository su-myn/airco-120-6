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

def process_ics_calendar(calendar_data, unit_id, source, source_identifier=None, user=None):
    """Process ICS calendar data and handle bookings based on confirmation codes - FIXED VERSION"""
    from icalendar import Calendar
    import re

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

    print(
        f"DEBUG: Found {len(current_bookings)} bookings in ICS with confirmation codes: {list(current_bookings.keys())}")

    # FIXED: Get existing bookings more intelligently - focus on confirmation codes
    current_codes = set(current_bookings.keys())

    if not current_codes:
        print("DEBUG: No valid confirmation codes found in ICS, exiting")
        return 0, 0, 0, []

    # Query for existing bookings with ANY of the confirmation codes from this ICS
    # This is more precise than filtering by source/unit alone
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
            print(
                f"DEBUG: Skipping duplicate booking {confirmation_code} - already exists with ID {duplicate_check.id}")
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
            notes=f"Auto-imported from {source}" + (f" ({source_identifier})" if source_identifier else ""),
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

    # FIXED: Handle cancelled bookings more carefully
    # Only cancel bookings that were imported by THIS specific source
    for booking in all_existing_bookings:
        if not booking.confirmation_code:
            continue

        # If this booking's confirmation code is not in current ICS
        if booking.confirmation_code not in current_codes:
            # Only cancel if this booking was imported from this specific source
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

            if should_cancel and booking.check_out_date >= datetime.utcnow().date() and not booking.is_cancelled:
                print(f"DEBUG: Marking booking {booking.confirmation_code} as cancelled")
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
            print(
                f"DEBUG: Successfully committed {bookings_added} new, {bookings_updated} updated, {bookings_cancelled} cancelled bookings")
        except Exception as e:
            print(f"ERROR: Failed to commit changes: {str(e)}")
            db.session.rollback()
            return 0, 0, 0, []

    return len(affected_units), len(affected_units), bookings_cancelled, affected_booking_ids


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


# Add this route to test the scheduler manually
# Add this to one of your route files (like calendar.py or create a new test route)

@calendar_bp.route('/test_sync')
@login_required
@permission_required('can_manage_bookings')
def test_sync():
    """Manual test route to trigger calendar sync"""
    try:
        from app import sync_all_calendars
        sync_all_calendars()
        flash('Calendar sync completed successfully!', 'success')
    except Exception as e:
        flash(f'Calendar sync failed: {str(e)}', 'danger')

    return redirect(url_for('calendar.import_ics'))


# Also add this route to check scheduler status
@calendar_bp.route('/scheduler_status')
@login_required
@permission_required('can_manage_bookings')
def scheduler_status():
    """Check scheduler status"""
    from app import scheduler

    if scheduler.running:
        jobs = scheduler.get_jobs()
        job_info = []
        for job in jobs:
            job_info.append({
                'id': job.id,
                'name': job.name,
                'next_run': str(job.next_run_time),
                'trigger': str(job.trigger)
            })

        return jsonify({
            'status': 'running',
            'jobs': job_info,
            'total_sync_jobs': len([j for j in jobs if 'sync_calendars' in j.id]),
            'sync_times': ['2:00 AM', '12:00 PM', '6:00 PM', '11:55 PM'],
            'timezone': 'Asia/Kuala_Lumpur'
        })
    else:
        return jsonify({
            'status': 'not running',
            'jobs': []
        })


@calendar_bp.route('/test_scheduler_status')
@login_required
@permission_required('can_manage_bookings')
def test_scheduler_status():
    """Test route to check scheduler status"""
    from app import scheduler

    status = {
        'running': scheduler.running if scheduler else False,
        'jobs': [],
        'calendar_sources': []
    }

    if scheduler and scheduler.running:
        jobs = scheduler.get_jobs()
        for job in jobs:
            if 'sync_calendars' in job.id:
                status['jobs'].append({
                    'id': job.id,
                    'name': job.name,
                    'next_run': str(job.next_run_time),
                    'trigger': str(job.trigger)
                })

    # Check calendar sources
    calendar_sources = CalendarSource.query.filter(
        CalendarSource.source_url.isnot(None),
        CalendarSource.source_url != '',
        CalendarSource.is_active == True
    ).all()

    for source in calendar_sources:
        status['calendar_sources'].append({
            'id': source.id,
            'unit': source.unit.unit_number,
            'source_name': source.source_name,
            'source_identifier': source.source_identifier,
            'last_updated': source.last_updated.strftime('%Y-%m-%d %H:%M:%S') if source.last_updated else 'Never',
            'url_present': bool(source.source_url)
        })

    return jsonify(status)


@calendar_bp.route('/test_manual_sync')
@login_required
@permission_required('can_manage_bookings')
def test_manual_sync():
    """Manually trigger calendar sync for testing"""
    try:
        from app import sync_all_calendars
        sync_all_calendars()
        flash('Manual sync completed successfully!', 'success')
    except Exception as e:
        flash(f'Manual sync failed: {str(e)}', 'danger')

    return redirect(url_for('calendar.import_ics'))


# 3. ADD this route to calendar.py to check the scheduler status and test sync:

@calendar_bp.route('/test_scheduler_debug')
@login_required
@permission_required('can_manage_calendar')
def test_scheduler_debug():
    """Debug route to check scheduler and test sync"""
    from app import scheduler

    debug_info = {
        'scheduler_running': scheduler.running if scheduler else False,
        'jobs': [],
        'environment': {
            'flask_env': os.environ.get('FLASK_ENV'),
            'disable_scheduler': os.environ.get('DISABLE_SCHEDULER'),
            'current_time': datetime.now().isoformat(),
        },
        'calendar_sources': []
    }

    # Get scheduler jobs
    if scheduler and scheduler.running:
        jobs = scheduler.get_jobs()
        for job in jobs:
            debug_info['jobs'].append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger),
                'func': str(job.func)
            })

    # Get calendar sources
    sources = CalendarSource.query.filter(
        CalendarSource.is_active == True,
        CalendarSource.source_url.isnot(None)
    ).all()

    for source in sources:
        debug_info['calendar_sources'].append({
            'id': source.id,
            'unit': source.unit.unit_number if source.unit else 'No Unit',
            'source': source.source_name,
            'identifier': source.source_identifier,
            'last_updated': source.last_updated.isoformat() if source.last_updated else None,
            'url_length': len(source.source_url) if source.source_url else 0
        })

    return jsonify(debug_info)


# 4. ADD this route to manually test the scheduled sync function:

@calendar_bp.route('/test_scheduled_sync')
@login_required
@permission_required('can_manage_calendar')
def test_scheduled_sync():
    """Test the exact same function that the scheduler calls"""
    try:
        from app import sync_all_calendars_with_context

        # Call the exact same function the scheduler uses
        result = sync_all_calendars_with_context()

        flash('Scheduled sync function test completed. Check the console/logs for details.', 'success')

    except Exception as e:
        flash(f'Error testing scheduled sync: {str(e)}', 'danger')

    return redirect(url_for('calendar.import_ics'))


@calendar_bp.route('/debug_sync_logs')
@login_required
def debug_sync_logs():
    """Show recent sync attempts"""
    sources = CalendarSource.query.filter(
        CalendarSource.is_active == True
    ).order_by(CalendarSource.last_updated.desc()).limit(10).all()

    return render_template_string("""
    <h2>Debug: Calendar Sync Status</h2>
    <p>Current time: {{ now }}</p>
    <table border="1">
        <tr><th>Unit</th><th>Source</th><th>Last Updated</th><th>URL Present</th></tr>
        {% for source in sources %}
        <tr>
            <td>{{ source.unit.unit_number }}</td>
            <td>{{ source.source_name }}</td>
            <td>{{ source.last_updated or 'Never' }}</td>
            <td>{{ 'Yes' if source.source_url else 'No' }}</td>
        </tr>
        {% endfor %}
    </table>
    """, sources=sources, now=datetime.now())


def process_ics_calendar_scheduled(calendar_data, unit_id, source, source_identifier=None, user_id=None):
    """Process ICS calendar data for scheduled jobs (without request context)"""
    from icalendar import Calendar
    import re

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
            notes=f"Auto-imported from {source}" + (f" ({source_identifier})" if source_identifier else ""),
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

    # Handle cancelled bookings
    for confirmation_code in existing_codes - current_codes:
        booking = existing_booking_map[confirmation_code]

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

        if should_cancel and booking.check_out_date >= datetime.utcnow().date():
            print(f"DEBUG: Marking booking {confirmation_code} as cancelled")
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