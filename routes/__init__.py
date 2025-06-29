def register_blueprints(app):
    """Register all blueprints with the Flask app"""
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.admin import admin_bp
    from routes.units import units_bp
    from routes.issues import issues_bp
    from routes.repairs import repairs_bp
    from routes.replacements import replacements_bp
    from routes.bookings import bookings_bp
    from routes.calendar import calendar_bp
    from routes.cleaners import cleaners_bp
    from routes.analytics import analytics_bp
    from routes.contacts import contacts_bp
    from routes.expenses import expenses_bp
    from routes.occupancy import occupancy_bp
    from routes.user_management import user_management_bp

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(units_bp)
    app.register_blueprint(issues_bp)
    app.register_blueprint(repairs_bp)
    app.register_blueprint(replacements_bp)
    app.register_blueprint(bookings_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(cleaners_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(contacts_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(occupancy_bp)
    app.register_blueprint(user_management_bp)