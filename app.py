# Add these imports at the top of app.py
from flask import Flask, render_template, session
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_apscheduler import APScheduler
import os
import pytz
from datetime import datetime, timedelta

from models import db, User, Role, Company, HolidayType
from config import config
from routes.calendar import process_ics_calendar
import requests
from models import CalendarSource


# Initialize extensions
bcrypt = Bcrypt()
login_manager = LoginManager()
migrate = Migrate()
scheduler = APScheduler()


def create_app(config_name=None):
    app = Flask(__name__)

    # Get config name from environment or use default
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    # Load configuration
    app.config.from_object(config[config_name])

    # Initialize extensions with app
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    migrate.init_app(app, db)

    # Add template filter for Malaysia timezone
    @app.template_filter('malaysia_time')
    def malaysia_time_filter(utc_dt):
        """Convert UTC datetime to Malaysia timezone"""
        if utc_dt is None:
            return ""
        malaysia_tz = pytz.timezone('Asia/Kuala_Lumpur')
        if utc_dt.tzinfo is None:
            utc_dt = pytz.utc.localize(utc_dt)
        malaysia_time = utc_dt.astimezone(malaysia_tz)
        return malaysia_time.strftime('%b %d, %Y, %I:%M %p')

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Import and register blueprints
    from routes import register_blueprints
    register_blueprints(app)

    # FIXED: Initialize scheduler in all environments
    # Only disable it explicitly if DISABLE_SCHEDULER is set
    if not os.environ.get('DISABLE_SCHEDULER'):
        init_scheduler(app)
        print(f"Scheduler initialized for environment: {config_name}")

    return app


# ... (keep all your existing functions: create_default_data, create_issue_items, etc.)
def create_default_data():
    """Create default data for the application"""
    admin_user = User.query.filter_by(email='admin@example.com').first()
    if not admin_user:
        # Check if default company exists
        default_company = Company.query.filter_by(name="Default Company").first()
        if not default_company:
            default_company = Company(
                name="Default Company",
                max_units=20
            )
            db.session.add(default_company)
            db.session.commit()
            print("Default company created")

        # Create default roles if they don't exist
        roles = {
            "Admin": {
                "can_view_complaints": True,
                "can_manage_complaints": True,
                "can_view_issues": True,
                "can_manage_issues": True,
                "can_view_repairs": True,
                "can_manage_repairs": True,
                "can_view_replacements": True,
                "can_manage_replacements": True,
                "can_view_bookings": True,
                "can_manage_bookings": True,
                "can_view_calendar": True,
                "can_manage_calendar": True,
                "can_view_occupancy": True,
                "can_manage_occupancy": True,
                "can_view_expenses": True,
                "can_manage_expenses": True,
                "can_view_contacts": True,
                "can_manage_contacts": True,
                "can_view_analytics": True,
                "can_manage_analytics": True,
                "can_view_units": True,
                "can_manage_units": True,
                "can_view_manage_cleaners": True,
                "can_manage_manage_cleaners": True,
                "can_view_jadual_pembersihan": True,
                "can_manage_jadual_pembersihan": True,
                "is_admin": True,
                "can_manage_users": True
            },
            "Manager": {
                "can_view_complaints": True,
                "can_manage_complaints": True,
                "can_view_issues": True,
                "can_manage_issues": True,
                "can_view_repairs": True,
                "can_manage_repairs": True,
                "can_view_replacements": True,
                "can_manage_replacements": True,
                "can_view_bookings": True,
                "can_manage_bookings": True,
                "can_view_calendar": True,
                "can_manage_calendar": True,
                "can_view_occupancy": True,
                "can_manage_occupancy": True,
                "can_view_expenses": True,
                "can_manage_expenses": True,
                "can_view_contacts": True,
                "can_manage_contacts": True,
                "can_view_analytics": True,
                "can_manage_analytics": True,
                "can_view_units": True,
                "can_manage_units": True,
                "can_view_manage_cleaners": True,
                "can_manage_manage_cleaners": True,
                "can_view_jadual_pembersihan": True,
                "can_manage_jadual_pembersihan": True,
                "is_admin": False,
                "can_manage_users": False
            },
            "Staff": {
                "can_view_complaints": True,
                "can_manage_complaints": False,
                "can_view_issues": True,
                "can_manage_issues": True,
                "can_view_repairs": True,
                "can_manage_repairs": False,
                "can_view_replacements": True,
                "can_manage_replacements": False,
                "can_view_bookings": True,
                "can_manage_bookings": True,
                "can_view_calendar": True,
                "can_manage_calendar": False,
                "can_view_occupancy": True,
                "can_manage_occupancy": False,
                "can_view_expenses": True,
                "can_manage_expenses": False,
                "can_view_contacts": True,
                "can_manage_contacts": False,
                "can_view_analytics": True,
                "can_manage_analytics": False,
                "can_view_units": True,
                "can_manage_units": False,
                "can_view_manage_cleaners": False,
                "can_manage_manage_cleaners": False,
                "can_view_jadual_pembersihan": True,
                "can_manage_jadual_pembersihan": False,
                "is_admin": False,
                "can_manage_users": False
            },
            "Technician": {
                "can_view_complaints": True,
                "can_manage_complaints": False,
                "can_view_repairs": True,
                "can_manage_repairs": True,
                "can_view_replacements": False,
                "can_manage_replacements": False,
                "is_admin": False,
                "can_manage_users": False
            },
            "Cleaner": {
                "can_view_complaints": True,
                "can_manage_complaints": False,
                "can_view_issues": True,
                "can_manage_issues": False,
                "can_view_repairs": False,
                "can_manage_repairs": False,
                "can_view_replacements": True,
                "can_manage_replacements": True,
                "can_view_jadual_pembersihan": True,
                "can_manage_jadual_pembersihan": False,
                "is_admin": False,
                "can_manage_users": False
            }
        }

        for role_name, permissions in roles.items():
            role = Role.query.filter_by(name=role_name).first()
            if not role:
                role = Role(name=role_name, **permissions)
                db.session.add(role)
                db.session.commit()
                print(f"Role '{role_name}' created")

        # Create admin user if no admin exists
        admin_role = Role.query.filter_by(name="Admin").first()
        admin = User.query.filter_by(is_admin=True).first()

        if not admin and admin_role:
            password = 'admin123'  # Default password
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            admin = User(
                name='Admin',
                email='admin@example.com',
                password=hashed_password,
                role_id=admin_role.id,
                company_id=default_company.id
            )
            db.session.add(admin)
            db.session.commit()
            print('Admin user created with email: admin@example.com and password: admin123')

        # Create a few sample units for the default company
        from models import Unit
        if Unit.query.count() == 0:
            sample_units = [
                {"unit_number": "A-101", "building": "Block A", "floor": 1, "description": "Corner unit",
                 "is_occupied": True},
                {"unit_number": "A-102", "building": "Block A", "floor": 1, "description": "Middle unit",
                 "is_occupied": True},
                {"unit_number": "B-201", "building": "Block B", "floor": 2, "description": "End unit",
                 "is_occupied": True},
                {"unit_number": "C-301", "building": "Block C", "floor": 3, "description": "Penthouse",
                 "is_occupied": False},
            ]

            for unit_data in sample_units:
                unit = Unit(
                    unit_number=unit_data["unit_number"],
                    building=unit_data["building"],
                    floor=unit_data["floor"],
                    description=unit_data["description"],
                    is_occupied=unit_data["is_occupied"],
                    company_id=default_company.id
                )
                db.session.add(unit)

            db.session.commit()
            print("Default data created successfully")
        else:
            print("Default data already exists")

    # Call the create_issue_defaults function
    create_issue_defaults()
    create_cleaner_role()
    create_holiday_types()


def create_issue_items():
    # Define issue items by category
    from models import Category, IssueItem
    issue_items_by_category = {
        "Building Issue": [
            "Carpark - Not Enough",
            "Carpark - Too High",
            "Lift - Waiting too long",
            "Swimming pool",
            "Noisy neighbour"
        ],
        "Cleaning Issue": [
            "Dusty",
            "Bedsheet - Not Clean",
            "Bedsheet - Smelly",
            "Toilet - Smelly",
            "Toilet Not Clean",
            "House - Smelly",
            "Got Ants",
            "Got Cockroach",
            "Got Insects",
            "Got mouse",
            "Not enough towels",
            "Not enough toiletries"
        ],
        "Plumbing Issues": [
            "Basin stucked",
            "Basin dripping",
            "Faucet Dripping",
            "Bidet dripping",
            "Toilet bowl stuck",
            "Shower head",
            "Toilet fitting lose",
            "Water pressure Low",
            "Drainage problem"
        ],
        "Electrical Issue": [
            "TV Box",
            "Internet WiFi",
            "Water Heater",
            "Fan",
            "Washing machine",
            "House No Electric",
            "Light",
            "Hair dryer",
            "Iron",
            "Microwave",
            "Kettle",
            "Remote control",
            "Induction Cooker",
            "Rice Cooker",
            "Water Filter",
            "Fridge"
        ],
        "Furniture Issue": [
            "Chair",
            "Sofa",
            "Wardrobe",
            "Kitchenware",
            "Bed",
            "Pillow",
            "Bedframe",
            "Iron board Cover",
            "Windows",
            "Coffee Table",
            "Cabinet",
            "Dining Table"
        ],
        "Check-in Issue": [
            "Access card Holder",
            "Access card",
            "key",
            "Letterbox - cant open",
            "Letterbox - left open",
            "Letterbox - missing",
            "Door",
            "Door Password"
        ],
        "Aircond Issue": [
            "AC not cold",
            "AC leaking",
            "AC noisy",
            "AC empty - tank"
        ]
    }

    # Get or create categories
    for category_name, items in issue_items_by_category.items():
        # Get or create the category
        category = Category.query.filter_by(name=category_name).first()
        if not category:
            category = Category(name=category_name)
            db.session.add(category)
            db.session.flush()  # Flush to get the category ID

        # Create issue items for this category
        for item_name in items:
            # Check if the issue item already exists
            existing_item = IssueItem.query.filter_by(name=item_name, category_id=category.id).first()
            if not existing_item:
                issue_item = IssueItem(name=item_name, category_id=category.id)
                db.session.add(issue_item)

    db.session.commit()
    print("Issue items created successfully")


def create_issue_defaults():
    # Create categories
    from models import Category, ReportedBy, Priority, Status, Type, IssueItem

    categories = ["Building Issue", "Cleaning Issue", "Plumbing Issues", "Electrical Issue", "Furniture Issue",
                  "Check-in Issue", "Aircond Issue"]
    for category_name in categories:
        if not Category.query.filter_by(name=category_name).first():
            category = Category(name=category_name)
            db.session.add(category)

    # Create reported by options
    reporters = ["Cleaner", "Guest", "Operator", "Head"]
    for reporter_name in reporters:
        if not ReportedBy.query.filter_by(name=reporter_name).first():
            reporter = ReportedBy(name=reporter_name)
            db.session.add(reporter)

    # Create priorities
    priorities = ["High", "Medium", "Low"]
    for priority_name in priorities:
        if not Priority.query.filter_by(name=priority_name).first():
            priority = Priority(name=priority_name)
            db.session.add(priority)

    # Create statuses
    statuses = ["Pending", "In Progress", "Resolved", "Rejected"]
    for status_name in statuses:
        if not Status.query.filter_by(name=status_name).first():
            status = Status(name=status_name)
            db.session.add(status)

    # Create types
    types = ["Repair", "Replace"]
    for type_name in types:
        if not Type.query.filter_by(name=type_name).first():
            type_obj = Type(name=type_name)
            db.session.add(type_obj)

    db.session.commit()

    # Create the issue items
    create_issue_items()
    print("Issue defaults created")


def create_cleaner_role():
    # Check if Cleaner role exists
    cleaner_role = Role.query.filter_by(name="Cleaner").first()
    if not cleaner_role:
        cleaner_role = Role(
            name="Cleaner",
            can_view_complaints=True,
            can_manage_complaints=False,
            can_view_issues=True,
            can_manage_issues=False,
            can_view_repairs=False,
            can_manage_repairs=False,
            can_view_replacements=False,
            can_manage_replacements=False,
            is_admin=False,
            can_manage_users=False
        )
        db.session.add(cleaner_role)
        db.session.commit()
        print("Cleaner role created")


def create_holiday_types():
    # Check if holiday types exist
    if HolidayType.query.count() == 0:
        # Create default holiday types
        holiday_types = [
            {"name": "Malaysia Public Holiday", "color": "#4CAF50", "is_system": True},
            {"name": "Malaysia School Holiday", "color": "#2196F3", "is_system": True},
            {"name": "Custom Holiday", "color": "#9C27B0", "is_system": True}
        ]

        for type_data in holiday_types:
            holiday_type = HolidayType(
                name=type_data["name"],
                color=type_data["color"],
                is_system=type_data["is_system"]
            )
            db.session.add(holiday_type)

        db.session.commit()
        print("Default holiday types created")


# FIXED: Create a wrapper function that runs with application context

def sync_all_calendars_with_context():
    """Wrapper function to run sync_all_calendars with application context"""
    try:
        print(f"=== SCHEDULED SYNC STARTING at {datetime.now()} ===")
        print(f"Current working directory: {os.getcwd()}")
        print(f"Flask app: {app}")
        print(f"App context: {app.app_context()}")

        with app.app_context():
            print("✓ App context established successfully")

            # Test database connection
            try:
                from models import CalendarSource
                source_count = CalendarSource.query.count()
                print(f"✓ Database connection OK - found {source_count} calendar sources")
            except Exception as db_error:
                print(f"✗ Database connection error: {db_error}")
                return

            # Test current_user context (this might be the issue)
            try:
                print(f"✓ About to call sync_all_calendars()")
                result = sync_all_calendars()
                print(f"✓ sync_all_calendars() completed with result: {result}")
            except Exception as sync_error:
                print(f"✗ Error in sync_all_calendars(): {sync_error}")
                import traceback
                traceback.print_exc()

    except Exception as e:
        print(f"✗ CRITICAL ERROR in sync_all_calendars_with_context: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"=== SCHEDULED SYNC ENDED at {datetime.now()} ===")


# FIXED: Improved sync function with better error handling and logging
def sync_all_calendars():
    """Sync all active calendar sources that have URLs - FIXED VERSION"""
    print(f"Starting calendar sync at {datetime.now()} Malaysia time...")

    try:
        # Import here to avoid circular imports
        from models import CalendarSource, User
        from routes.calendar import process_ics_calendar_scheduled  # Add this import

        # Rest of your function remains the same...
        # Get all active calendar sources with URLs
        calendar_sources = CalendarSource.query.filter(
            CalendarSource.source_url.isnot(None),
            CalendarSource.source_url != '',
            CalendarSource.is_active == True
        ).all()

        if not calendar_sources:
            print("No active calendar sources found for syncing.")
            return {"success": True, "message": "No sources to sync"}

        print(f"Found {len(calendar_sources)} calendar sources to sync.")

        sync_success_count = 0
        sync_error_count = 0
        sync_results = []

        for source in calendar_sources:
            source_result = {
                'source_id': source.id,
                'unit_number': source.unit.unit_number if source.unit else 'Unknown',
                'source_name': source.source_name,
                'success': False,
                'error': None,
                'added': 0,
                'updated': 0,
                'cancelled': 0
            }

            try:
                # Validate that the unit still exists
                if not source.unit:
                    error_msg = f"Unit for calendar source {source.id} no longer exists"
                    print(f"Error: {error_msg}")
                    source_result['error'] = error_msg
                    sync_error_count += 1
                    sync_results.append(source_result)
                    continue

                print(f"Syncing {source.source_identifier or source.source_name} for unit {source.unit.unit_number}...")
                print(f"URL: {source.source_url}")

                # Download the ICS file with timeout and better error handling
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

                print(f"Response status: {response.status_code}")

                if response.status_code == 200:
                    calendar_data = response.text
                    print(f"Downloaded calendar data, length: {len(calendar_data)}")

                    # Get the admin user for this company
                    admin_user = User.query.filter_by(
                        company_id=source.unit.company_id,
                        is_admin=True
                    ).first()

                    if not admin_user:
                        # Fallback: get any user from the same company
                        admin_user = User.query.filter_by(
                            company_id=source.unit.company_id
                        ).first()

                    if not admin_user:
                        error_msg = f"No user found for company {source.unit.company_id}"
                        print(f"Error: {error_msg}")
                        source_result['error'] = error_msg
                        sync_error_count += 1
                        sync_results.append(source_result)
                        continue

                    # FIXED: Pass the user_id instead of trying to login
                    units_added, units_updated, bookings_cancelled, affected_booking_ids = process_ics_calendar_scheduled(
                        calendar_data,
                        source.unit_id,
                        source.source_name,
                        source.source_identifier or source.source_name,
                        admin_user.id  # Pass user ID instead of logging in
                    )

                    # Update the last_updated timestamp
                    source.last_updated = datetime.utcnow()
                    db.session.commit()

                    # Record results
                    source_result.update({
                        'success': True,
                        'added': units_added,
                        'updated': units_updated,
                        'cancelled': bookings_cancelled
                    })

                    sync_success_count += 1
                    print(f"✓ Successfully synced {source.source_identifier or source.source_name} for unit {source.unit.unit_number}")
                    print(f"  - Added: {units_added}, Updated: {units_updated}, Cancelled: {bookings_cancelled}")

                else:
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    print(f"Failed to download calendar from {source.source_url} - {error_msg}")
                    source_result['error'] = error_msg
                    sync_error_count += 1

            except requests.exceptions.Timeout:
                error_msg = "Request timeout (30s)"
                print(f"Timeout while syncing calendar for {source.unit.unit_number if source.unit else 'Unknown Unit'}")
                source_result['error'] = error_msg
                sync_error_count += 1

            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                print(f"Error syncing calendar for {source.unit.unit_number if source.unit else 'Unknown Unit'}: {error_msg}")
                import traceback
                traceback.print_exc()
                source_result['error'] = error_msg
                sync_error_count += 1

            finally:
                sync_results.append(source_result)

        print(f"Calendar sync completed. Success: {sync_success_count}, Errors: {sync_error_count}")

        # Return detailed results
        return {
            "success": sync_error_count == 0,
            "total_sources": len(calendar_sources),
            "successful": sync_success_count,
            "failed": sync_error_count,
            "results": sync_results
        }

    except Exception as e:
        error_msg = f"CRITICAL ERROR in sync_all_calendars: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": error_msg
        }


# FIXED: Initialize scheduler with Malaysia timezone
def init_scheduler(app):
    # Set scheduler configuration for Malaysia timezone
    app.config['SCHEDULER_TIMEZONE'] = 'Asia/Kuala_Lumpur'
    app.config['SCHEDULER_API_ENABLED'] = False  # Disable API for security

    scheduler.init_app(app)
    scheduler.start()

    # FIXED: Schedule multiple sync tasks throughout the day
    # Using Malaysia timezone for all cron jobs
    malaysia_tz = pytz.timezone('Asia/Kuala_Lumpur')


    # 2:00 AM Malaysia time
    scheduler.add_job(
        func=sync_all_calendars_with_context,  # Use the wrapper function
        trigger='cron',
        hour=2,
        minute=0,
        timezone=malaysia_tz,
        id='sync_calendars_200am',
        name='Calendar Sync - 2:00 AM',
        replace_existing=True
    )

    # TESTING 9:55 PM Malaysia time
    scheduler.add_job(
        func=sync_all_calendars_with_context,  # Use the wrapper function
        trigger='cron',
        hour=21,
        minute=55,
        timezone=malaysia_tz,
        id='sync_calendars_955pm',
        name='Calendar Sync - 9:55 PM',
        replace_existing=True
    )

    # 9:00 AM (Noon) Malaysia time
    scheduler.add_job(
        func=sync_all_calendars_with_context,  # Use the wrapper function
        trigger='cron',
        hour=9,
        minute=0,
        timezone=malaysia_tz,
        id='sync_calendars_9am',
        name='Calendar Sync - 9:00 AM',
        replace_existing=True
    )

    # 12:00 PM (Noon) Malaysia time
    scheduler.add_job(
        func=sync_all_calendars_with_context,  # Use the wrapper function
        trigger='cron',
        hour=12,
        minute=0,
        timezone=malaysia_tz,
        id='sync_calendars_12pm',
        name='Calendar Sync - 12:00 PM',
        replace_existing=True
    )

    # 3:00 PM Malaysia time
    scheduler.add_job(
        func=sync_all_calendars_with_context,  # Use the wrapper function
        trigger='cron',
        hour=15,
        minute=0,
        timezone=malaysia_tz,
        id='sync_calendars_300pm',
        name='Calendar Sync - 3:00 PM',
        replace_existing=True
    )

    # 6:00 PM Malaysia time
    scheduler.add_job(
        func=sync_all_calendars_with_context,  # Use the wrapper function
        trigger='cron',
        hour=18,
        minute=0,
        timezone=malaysia_tz,
        id='sync_calendars_600pm',
        name='Calendar Sync - 6:00 PM',
        replace_existing=True
    )

    # 6:35 PM Malaysia time
    scheduler.add_job(
        func=sync_all_calendars_with_context,  # Use the wrapper function
        trigger='cron',
        hour=18,
        minute=35,
        timezone=malaysia_tz,
        id='sync_calendars_635pm',
        name='Calendar Sync - 6:35 PM',
        replace_existing=True
    )

    # 9:00 PM Malaysia time
    scheduler.add_job(
        func=sync_all_calendars_with_context,  # Use the wrapper function
        trigger='cron',
        hour=21,
        minute=0,
        timezone=malaysia_tz,
        id='sync_calendars_900pm',
        name='Calendar Sync - 9:00 PM',
        replace_existing=True
    )

    # 11:55 PM Malaysia time
    scheduler.add_job(
        func=sync_all_calendars_with_context,  # Use the wrapper function
        trigger='cron',
        hour=23,
        minute=55,
        timezone=malaysia_tz,
        id='sync_calendars_1155pm',
        name='Calendar Sync - 11:55 PM',
        replace_existing=True
    )

    print("Scheduler started successfully!")
    print("Calendar sync scheduled for:")
    print("  - 2:00 AM Malaysia time")
    print("  - 9:00 AM Malaysia time")
    print("  - 12:00 PM Malaysia time")
    print("  - 3:00 PM Malaysia time")
    print("  - 6:00 PM Malaysia time")
    print("  - 6:35 PM Malaysia time")
    print("  - 9:00 PM Malaysia time")
    print("  - 11:55 PM Malaysia time")

    # Log all scheduled jobs for debugging
    jobs = scheduler.get_jobs()
    print(f"\nTotal jobs scheduled: {len(jobs)}")
    for job in jobs:
        print(f"  - {job.name} (ID: {job.id}) - Next run: {job.next_run_time}")

    # OPTIONAL: Add a test job that runs every 5 minutes for debugging
    # Remove this in production
    if os.environ.get('DEBUG_SCHEDULER'):
        scheduler.add_job(
            func=lambda: print(f"Test scheduler job running at {datetime.now()}"),
            trigger='interval',
            minutes=5,
            id='test_scheduler',
            name='Test Scheduler',
            replace_existing=True
        )
        print("Debug scheduler job added (runs every 5 minutes)")


# Create app instance
app = create_app()

# Create the database tables and default data
with app.app_context():
    db.create_all()
    create_default_data()

if __name__ == '__main__':
    app.run(debug=True)