from racelab.car import Car


def sports_car(**changes) -> Car:
    """Baseline test car; keyword arguments override fields."""
    fields = dict(
        name="Sports",
        mass_kg=1300.0,
        power_w=250e3,
        drag_coefficient=0.32,
        frontal_area_m2=2.0,
        tire_friction=1.1,
        max_braking_decel_mps2=10.0,
        max_tractive_force_n=9000.0,
        drivetrain_efficiency=0.88,
    )
    fields.update(changes)
    return Car(**fields)
