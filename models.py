from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()


# AccountType model
class AccountType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    max_units = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"AccountType('{self.name}', max_units={self.max_units})"


# Company model
class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    max_units = db.Column(db.Integer, nullable=False, default=20)

    # User limits by role
    max_manager_users = db.Column(db.Integer, nullable=False, default=1)
    max_staff_users = db.Column(db.Integer, nullable=False, default=1)
    max_cleaner_users = db.Column(db.Integer, nullable=False, default=2)

    users = db.relationship('User', backref='company', lazy=True)

    def get_user_count_by_role(self, role_name):
        """Get current count of users for a specific role in this company"""
        return User.query.join(Role).filter(
            User.company_id == self.id,
            Role.name == role_name
        ).count()

    def can_add_user_for_role(self, role_name):
        """Check if company can add another user for the specified role"""
        current_count = self.get_user_count_by_role(role_name)

        if role_name == 'Manager':
            return current_count < self.max_manager_users
        elif role_name == 'Staff':
            return current_count < self.max_staff_users
        elif role_name == 'Cleaner':
            return current_count < self.max_cleaner_users

        return False

    def get_max_users_for_role(self, role_name):
        """Get maximum allowed users for a specific role"""
        if role_name == 'Manager':
            return self.max_manager_users
        elif role_name == 'Staff':
            return self.max_staff_users
        elif role_name == 'Cleaner':
            return self.max_cleaner_users

        return 0

    def __repr__(self):
        return f"Company('{self.name}', max_units={self.max_units})"


# Role model
class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)

    # Role permissions
    can_view_complaints = db.Column(db.Boolean, default=False)
    can_manage_complaints = db.Column(db.Boolean, default=False)

    can_view_issues = db.Column(db.Boolean, default=False)
    can_manage_issues = db.Column(db.Boolean, default=False)

    can_view_repairs = db.Column(db.Boolean, default=False)
    can_manage_repairs = db.Column(db.Boolean, default=False)

    can_view_replacements = db.Column(db.Boolean, default=False)
    can_manage_replacements = db.Column(db.Boolean, default=False)

    can_view_bookings = db.Column(db.Boolean, default=False)
    can_manage_bookings = db.Column(db.Boolean, default=False)

    # Calendar permissions
    can_view_calendar = db.Column(db.Boolean, default=False)
    can_manage_calendar = db.Column(db.Boolean, default=False)

    # Occupancy permissions
    can_view_occupancy = db.Column(db.Boolean, default=False)
    can_manage_occupancy = db.Column(db.Boolean, default=False)

    # Expenses permissions
    can_view_expenses = db.Column(db.Boolean, default=False)
    can_manage_expenses = db.Column(db.Boolean, default=False)

    # Contacts permissions
    can_view_contacts = db.Column(db.Boolean, default=False)
    can_manage_contacts = db.Column(db.Boolean, default=False)

    # Analytics permissions
    can_view_analytics = db.Column(db.Boolean, default=False)
    can_manage_analytics = db.Column(db.Boolean, default=False)

    # Units permissions
    can_view_units = db.Column(db.Boolean, default=False)
    can_manage_units = db.Column(db.Boolean, default=False)

    # Manage Cleaners permissions
    can_view_manage_cleaners = db.Column(db.Boolean, default=False)
    can_manage_manage_cleaners = db.Column(db.Boolean, default=False)

    # Jadual Pembersihan (Cleaning Schedule) permissions
    can_view_jadual_pembersihan = db.Column(db.Boolean, default=False)
    can_manage_jadual_pembersihan = db.Column(db.Boolean, default=False)

    # Admin permissions
    is_admin = db.Column(db.Boolean, default=False)
    can_manage_users = db.Column(db.Boolean, default=False)

    users = db.relationship('User', backref='role', lazy=True)

    def __repr__(self):
        return f"Role('{self.name}')"


# Create a many-to-many relationship between cleaners and units
cleaner_units = db.Table('cleaner_units',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('unit_id', db.Integer, db.ForeignKey('unit.id'), primary_key=True)
)

# Create a many-to-many relationship between staff users and units
staff_units = db.Table('staff_units',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('unit_id', db.Integer, db.ForeignKey('unit.id'), primary_key=True)
)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    # Remove: account_type_id = db.Column(db.Integer, db.ForeignKey('account_type.id'), nullable=False, default=1)
    # Remove: account_type = db.relationship('AccountType', backref='users')

    # Foreign keys for company and role
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    is_cleaner = db.Column(db.Boolean, default=False)

    # Relationships
    complaints = db.relationship('Complaint', backref='author', lazy=True)
    issues = db.relationship('Issue', backref='author', lazy=True)
    repairs = db.relationship('Repair', backref='author', lazy=True)
    replacements = db.relationship('Replacement', backref='author', lazy=True)
    assigned_units = db.relationship('Unit', secondary=cleaner_units,
                                     backref=db.backref('assigned_cleaners', lazy='dynamic'))

    # Add this new relationship for staff unit assignments
    assigned_staff_units = db.relationship('Unit', secondary=staff_units,
                                         backref=db.backref('assigned_staff', lazy='dynamic'))

    def get_accessible_units(self):
        """Get units that this user can access based on their role"""
        if self.role.name == 'Admin' or self.is_admin:
            # Admins can see all units in their company
            return Unit.query.filter_by(company_id=self.company_id).all()
        elif self.role.name == 'Manager':
            # Managers can see all units in their company
            return Unit.query.filter_by(company_id=self.company_id).all()
        elif self.role.name == 'Staff':
            # Staff can only see units assigned to them
            return list(self.assigned_staff_units)
        elif self.role.name == 'Cleaner':
            # Cleaners can see units assigned to them for cleaning
            return list(self.assigned_units)
        else:
            # Default: no units accessible
            return []

    def get_accessible_unit_ids(self):
        """Get IDs of units that this user can access"""
        return [unit.id for unit in self.get_accessible_units()]


    def can_access_unit(self, unit_id):
        """Check if user can access a specific unit"""
        # Convert unit_id to int to handle form data (strings)
        try:
            unit_id = int(unit_id)
        except (ValueError, TypeError):
            return False

        if self.role.name in ['Admin', 'Manager'] or self.is_admin:
            # Admins and Managers can access all units in their company
            unit = Unit.query.get(unit_id)
            return unit and unit.company_id == self.company_id
        elif self.role.name == 'Staff':
            # Staff can only access assigned units
            return unit_id in self.get_accessible_unit_ids()
        elif self.role.name == 'Cleaner':
            # Cleaners can access units assigned for cleaning
            return unit_id in [unit.id for unit in self.assigned_units]
        else:
            return False

    @property
    def is_admin(self):
        return self.role.is_admin

    def has_permission(self, permission):
        """Check if user has a specific permission, considering custom overrides and role defaults"""

        # Admin users have all permissions
        if self.role.is_admin:
            return True

        # Managers get their role permissions by default
        if self.role.name == 'Manager':
            return getattr(self.role, permission, False)

        # For Staff and Cleaner roles, check custom permissions first
        # If no custom permissions exist, deny by default (managers control access explicitly)
        if self.role.name in ['Staff', 'Cleaner']:
            custom_perms = CustomUserPermission.query.filter_by(
                user_id=self.id,
                company_id=self.company_id
            ).first()

            if custom_perms:
                # If custom permissions exist, check the custom value
                custom_value = getattr(custom_perms, permission, None)
                if custom_value is not None:  # explicit True or False
                    return custom_value

            # If no custom permissions exist for Staff/Cleaner, deny by default
            return False

        # For any other roles, use role defaults
        role_permission = getattr(self.role, permission, False)
        return role_permission

    def __repr__(self):
        return f"User('{self.name}', '{self.email}', '{self.company.name}', '{self.role.name}')"


class Unit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unit_number = db.Column(db.String(20), nullable=False)  # Remove unique=True here
    description = db.Column(db.String(200))
    floor = db.Column(db.Integer)
    building = db.Column(db.String(100))
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    is_occupied = db.Column(db.Boolean, default=True)

    # Existing fields
    toilet_count = db.Column(db.Integer, nullable=True)
    towel_count = db.Column(db.Integer, nullable=True)
    max_pax = db.Column(db.Integer, nullable=True)

    # New fields
    letterbox_code = db.Column(db.String(50), nullable=True)
    smartlock_code = db.Column(db.String(50), nullable=True)
    wifi_name = db.Column(db.String(100), nullable=True)
    wifi_password = db.Column(db.String(100), nullable=True)
    bedrooms = db.Column(db.Integer, nullable=True)
    bathrooms = db.Column(db.Float, nullable=True)
    sq_ft = db.Column(db.Integer, nullable=True)
    default_toilet_paper = db.Column(db.Integer, nullable=True)
    default_towel = db.Column(db.Integer, nullable=True)
    default_garbage_bag = db.Column(db.Integer, nullable=True)
    monthly_rent = db.Column(db.Numeric(10, 2), nullable=True)
    address = db.Column(db.String(200), nullable=True)

    # Relationships
    company = db.relationship('Company', backref='units')
    complaints = db.relationship('Complaint', backref='unit_details', lazy=True)
    repairs = db.relationship('Repair', backref='unit_details', lazy=True)
    replacements = db.relationship('Replacement', backref='unit_details', lazy=True)

    # Add a composite unique constraint for unit_number and company_id
    __table_args__ = (db.UniqueConstraint('unit_number', 'company_id', name='_unit_company_uc'),)

    def __repr__(self):
        return f"Unit('{self.unit_number}', Building: '{self.building}')"

    def get_assigned_staff(self):
        """Get staff members assigned to this unit"""
        return [user for user in self.assigned_staff if user.role.name == 'Staff']


# New models for Issue functionality
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f"Category('{self.name}')"


class ReportedBy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f"ReportedBy('{self.name}')"


class Priority(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f"Priority('{self.name}')"


class Status(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f"Status('{self.name}')"


class Type(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f"Type('{self.name}')"


class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(100), nullable=False)
    remark = db.Column(db.String(200))
    unit = db.Column(db.String(20), nullable=False)  # Keep for backward compatibility
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'))
    date_added = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    company = db.relationship('Company', backref='complaints')

    def __repr__(self):
        return f"Complaint('{self.item}', '{self.unit}')"


class IssueItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))

    # Relationship to Category
    category = db.relationship('Category', backref='issue_items')

    def __repr__(self):
        return f"IssueItem('{self.name}')"


class Issue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=False)
    unit = db.Column(db.String(20), nullable=False)  # Keep for backward compatibility
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'))
    date_added = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # New fields
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    reported_by_id = db.Column(db.Integer, db.ForeignKey('reported_by.id'), nullable=True)
    priority_id = db.Column(db.Integer, db.ForeignKey('priority.id'), nullable=True)
    status_id = db.Column(db.Integer, db.ForeignKey('status.id'), nullable=True)
    type_id = db.Column(db.Integer, db.ForeignKey('type.id'), nullable=True)
    issue_item_id = db.Column(db.Integer, db.ForeignKey('issue_item.id'), nullable=True)  # New field
    solution = db.Column(db.Text, nullable=True)
    guest_name = db.Column(db.String(100), nullable=True)
    cost = db.Column(db.Numeric(10, 2), nullable=True)
    assigned_to = db.Column(db.String(100), nullable=True)

    # Original fields
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    # Relationships
    category = db.relationship('Category', backref='issues')
    reported_by = db.relationship('ReportedBy', backref='issues')
    priority = db.relationship('Priority', backref='issues')
    status = db.relationship('Status', backref='issues')
    type = db.relationship('Type', backref='issues')
    issue_item = db.relationship('IssueItem', backref='issues')  # New relationship
    company = db.relationship('Company', backref='issues')

    def __repr__(self):
        return f"Issue('{self.description}', '{self.unit}')"


class Repair(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(100), nullable=False)
    remark = db.Column(db.String(200))
    unit = db.Column(db.String(20), nullable=False)  # Keep for backward compatibility
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'))
    status = db.Column(db.String(50), default='Pending')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    company = db.relationship('Company', backref='repairs')

    def __repr__(self):
        return f"Repair('{self.item}', '{self.unit}', '{self.status}')"


class Replacement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(100), nullable=False)
    remark = db.Column(db.String(200))
    unit = db.Column(db.String(20), nullable=False)  # Keep for backward compatibility
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'))
    date_requested = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(50), default='Pending')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    company = db.relationship('Company', backref='replacements')

    def __repr__(self):
        return f"Replacement('{self.item}', '{self.unit}', '{self.status}')"


# Add this to your BookingForm model in models.py

class BookingForm(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    guest_name = db.Column(db.String(100), nullable=False)
    contact_number = db.Column(db.String(20), nullable=False)
    check_in_date = db.Column(db.Date, nullable=False)
    check_out_date = db.Column(db.Date, nullable=False)
    property_name = db.Column(db.String(100), nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'), nullable=False)
    unit = db.relationship('Unit', backref='bookings')
    number_of_nights = db.Column(db.Integer, nullable=False)
    number_of_guests = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    booking_source = db.Column(db.String(50), nullable=False)
    payment_status = db.Column(db.String(50), nullable=False, default='Pending')
    notes = db.Column(db.Text, nullable=True)

    # New fields
    confirmation_code = db.Column(db.String(50), nullable=True)
    adults = db.Column(db.Integer, nullable=True)
    children = db.Column(db.Integer, nullable=True)
    infants = db.Column(db.Integer, nullable=True)
    booking_date = db.Column(db.Date, nullable=True)

    # New field for cancelled bookings
    is_cancelled = db.Column(db.Boolean, default=False)

    # ADD THESE TWO NEW FIELDS:
    import_source = db.Column(db.String(200), nullable=True)  # Hidden from user
    import_timestamp = db.Column(db.DateTime, nullable=True)  # When imported

    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    company = db.relationship('Company', backref='bookings')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author = db.relationship('User', backref='bookings')
    date_added = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"Booking('{self.guest_name}', '{self.unit.unit_number}', Check-in: '{self.check_in_date}')"


class CalendarSource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'), nullable=False)
    source_name = db.Column(db.String(100), nullable=False)  # e.g., "Airbnb", "Booking.com"
    source_identifier = db.Column(db.String(200), nullable=True)  # New field: custom name/identifier
    source_url = db.Column(db.String(1000), nullable=True)  # URL if imported from URL
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)  # New field: to enable/disable sources

    unit = db.relationship('Unit', backref='calendar_sources')

    def __repr__(self):
        identifier = self.source_identifier or self.source_name
        return f"CalendarSource('{identifier}', '{self.unit.unit_number}')"


class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(50))
    building = db.Column(db.String(100))
    favourite = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    date_added = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    # Relationships
    company = db.relationship('Company', backref='contacts')
    user = db.relationship('User', backref='contacts')

    def __repr__(self):
        return f"Contact('{self.full_name}', '{self.role}')"


class ExpenseData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)

    # Revenue
    sales = db.Column(db.String(50), nullable=True)

    # Expenses
    rental = db.Column(db.String(50), nullable=True)
    electricity = db.Column(db.String(50), nullable=True)
    water = db.Column(db.String(50), nullable=True)
    sewage = db.Column(db.String(50), nullable=True)
    internet = db.Column(db.String(50), nullable=True)
    cleaner = db.Column(db.String(50), nullable=True)
    laundry = db.Column(db.String(50), nullable=True)
    supplies = db.Column(db.String(50), nullable=True)
    repair = db.Column(db.String(50), nullable=True)
    replace = db.Column(db.String(50), nullable=True)
    other = db.Column(db.String(50), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    company = db.relationship('Company', backref='expense_data')
    unit = db.relationship('Unit', backref='expense_data')

    # Composite unique constraint to ensure only one record per unit per month
    __table_args__ = (
        db.UniqueConstraint('company_id', 'unit_id', 'year', 'month', name='unique_unit_expense_monthly'),
    )

    def __repr__(self):
        return f"ExpenseData(Unit: {self.unit_id}, {self.month}/{self.year})"


# Add this to your models.py file
class ExpenseRemark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    column_name = db.Column(db.String(50), nullable=False)
    remark = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    company = db.relationship('Company', backref='expense_remarks')
    unit = db.relationship('Unit', backref='expense_remarks')

    # Composite unique constraint to ensure only one remark per unit per month per column
    __table_args__ = (
        db.UniqueConstraint('company_id', 'unit_id', 'year', 'month', 'column_name', name='unique_unit_expense_remark'),
    )

    def __repr__(self):
        return f"ExpenseRemark(Unit: {self.unit_id}, {self.month}/{self.year}, Column: {self.column_name})"


# Holiday models
class HolidayType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(20), nullable=False)
    is_system = db.Column(db.Boolean, default=False)  # True for system types that can't be deleted


class Holiday(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    holiday_type_id = db.Column(db.Integer, db.ForeignKey('holiday_type.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'))
    is_recurring = db.Column(db.Boolean, default=False)  # For annual holidays
    is_deleted = db.Column(db.Boolean, default=False)  # For marking system holidays as deleted for a company

    # Relationships
    holiday_type = db.relationship('HolidayType', backref='holidays')
    company = db.relationship('Company', backref='holidays')


# Add this new model to your models.py
class BookingCalendarSource(db.Model):
    """Mapping table to track which calendar source imported which booking"""
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking_form.id'), nullable=False)
    calendar_source_id = db.Column(db.Integer, db.ForeignKey('calendar_source.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    booking = db.relationship('BookingForm', backref='calendar_sources')
    calendar_source = db.relationship('CalendarSource', backref='bookings')

    # Ensure one booking can only be linked to one calendar source
    __table_args__ = (db.UniqueConstraint('booking_id', 'calendar_source_id', name='_booking_source_uc'),)


class CustomUserPermission(db.Model):
    """Custom permissions for individual users, allowing managers to override role permissions"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    # Bookings permissions
    can_view_bookings = db.Column(db.Boolean, default=None)  # None = use role default
    can_manage_bookings = db.Column(db.Boolean, default=None)

    # Calendar permissions
    can_view_calendar = db.Column(db.Boolean, default=None)
    can_manage_calendar = db.Column(db.Boolean, default=None)

    # Occupancy permissions
    can_view_occupancy = db.Column(db.Boolean, default=None)
    can_manage_occupancy = db.Column(db.Boolean, default=None)

    # Issues permissions
    can_view_issues = db.Column(db.Boolean, default=None)
    can_manage_issues = db.Column(db.Boolean, default=None)

    # Analytics permissions
    can_view_analytics = db.Column(db.Boolean, default=None)
    can_manage_analytics = db.Column(db.Boolean, default=None)

    # Expenses permissions
    can_view_expenses = db.Column(db.Boolean, default=None)
    can_manage_expenses = db.Column(db.Boolean, default=None)

    # Contacts permissions
    can_view_contacts = db.Column(db.Boolean, default=None)
    can_manage_contacts = db.Column(db.Boolean, default=None)

    # Units permissions
    can_view_units = db.Column(db.Boolean, default=None)
    can_manage_units = db.Column(db.Boolean, default=None)

    # Cleaner management permissions
    can_view_manage_cleaners = db.Column(db.Boolean, default=None)
    can_manage_manage_cleaners = db.Column(db.Boolean, default=None)

    # Cleaning schedule permissions
    can_view_jadual_pembersihan = db.Column(db.Boolean, default=None)
    can_manage_jadual_pembersihan = db.Column(db.Boolean, default=None)

    # Repair permissions
    can_view_repairs = db.Column(db.Boolean, default=None)
    can_manage_repairs = db.Column(db.Boolean, default=None)

    # Replacement permissions
    can_view_replacements = db.Column(db.Boolean, default=None)
    can_manage_replacements = db.Column(db.Boolean, default=None)

    # Relationships
    user = db.relationship('User', backref='custom_permissions')
    company = db.relationship('Company', backref='custom_permissions')

    # Ensure one record per user per company
    __table_args__ = (db.UniqueConstraint('user_id', 'company_id', name='_user_company_permissions_uc'),)

    def __repr__(self):
        return f"CustomUserPermission(user_id={self.user_id}, company_id={self.company_id})"

