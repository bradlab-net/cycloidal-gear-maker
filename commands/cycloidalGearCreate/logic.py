import json
import math
import traceback

import adsk.core
import adsk.fusion

from ...lib import fusion360utils as futil
from .settings import CycloidalGearSettings

app = adsk.core.Application.get()
ui = app.userInterface
skip_validate: bool = False


class CycloidalGearLogic:
    ATTRIBUTE_GROUP: str = "CycloidalGear"
    SETTINGS_ATTRIBUTE: str = "settings"

    def __init__(self, des: adsk.fusion.Design):
        setting_attribute = des.attributes.itemByName(
            CycloidalGearLogic.ATTRIBUTE_GROUP, CycloidalGearLogic.SETTINGS_ATTRIBUTE
        )
        self._app: adsk.core.Application = adsk.core.Application.get()
        self._ui: adsk.core.UserInterface = app.userInterface
        self._design: adsk.fusion.Design = adsk.fusion.Design.cast(app.activeProduct)
        self._root: adsk.fusion.Component = self._design.rootComponent

        self._settings: CycloidalGearSettings
        if setting_attribute is not None:
            json_settings: dict = json.loads(setting_attribute.value)
            self._settings = CycloidalGearSettings(**json_settings)
            futil.log(f"Settings loaded from attribute")
        else:
            self._settings = CycloidalGearSettings()
            futil.log(f"Settings not found")

        self._attributes: dict = {}
        self._properties: dict = {}

    def CreateCommandInputs(self, inputs: adsk.core.CommandInputs):
        global skip_validate
        skip_validate = True

        variables_tab = inputs.addTabCommandInput("variables_tab", "Variables")

        fields: dict = self._settings.get_fields()
        field_name: str
        for field_name in fields:
            field = fields[field_name]

            field_value = self._settings.__getattribute__(field_name)
            canonical_name: str = field.metadata.get("canonical_name", field_name)
            unit_type: str = field.metadata.get("units", "")

            if type(field_value) is float:
                input = variables_tab.children.addValueInput(
                    id=field_name,
                    name=canonical_name,
                    unitType=unit_type,
                    initialValue=adsk.core.ValueInput.createByReal(field_value),
                )
            elif type(field_value is int):
                input = variables_tab.children.addValueInput(
                    id=field_name,
                    name=canonical_name,
                    unitType=unit_type,
                    initialValue=adsk.core.ValueInput.createByString(str(field_value)),
                )
            else:
                input = variables_tab.children.addTextBoxCommandInput(
                    id=field_name,
                    name=canonical_name,
                    formattedText=str(field_value),
                    numRows=1,
                    isReadOnly=False,
                )

            self._attributes[field_name] = input

        calculated_values_tab = inputs.addTabCommandInput(
            "calculated_values_tab", "Calculated Values"
        )

        properties: list = self._settings.get_properties()
        property_name: str
        for property_name in properties:
            canonical_name: str = properties[property_name]["canonical_name"]
            input = calculated_values_tab.children.addTextBoxCommandInput(
                property_name,
                canonical_name,
                "",
                1,
                True,
            )

            self._properties[property_name] = input

        skip_validate = False

    def HandleInputsChanged(self, args: adsk.core.InputChangedEventArgs):
        if skip_validate:
            return

        changed_input = args.input

        # Save the attribute values
        self._save_attributes()

        # Update the calculated values
        properties: list = self._settings.get_properties()
        property_name: str
        for property_name in properties:
            units: str = properties[property_name].get("units", "")
            value = self._settings.__getattribute__(property_name)

            text: str
            if type(value) is str:
                text = value
            else:
                text = self._design.unitsManager.formatInternalValue(
                    value, units, units != ""
                )
            self._properties[property_name].text = text

    def HandleValidateInputs(self, args: adsk.core.ValidateInputsEventArgs):
        if not skip_validate:
            pass

        # inputs = args.inputs

        # # Verify the validity of the input values. This controls if the OK button is enabled or not.
        # valueInput = inputs.itemById("value_input")
        # if valueInput.value >= 0:
        #     args.areInputsValid = True
        # else:
        #     args.areInputsValid = False

    def HandleExecute(self, args: adsk.core.CommandEventArgs):
        if skip_validate:
            return

        self._save_attributes()

        des: adsk.fusion.Design = adsk.fusion.Design.cast(app.activeProduct)
        settings_jsons = self._settings.dumps()
        des.attributes.add(
            CycloidalGearLogic.ATTRIBUTE_GROUP,
            CycloidalGearLogic.SETTINGS_ATTRIBUTE,
            settings_jsons,
        )

        self._draw_gear()

    def _save_attributes(self):
        attribute_name: str
        for attribute_name in self._attributes:
            self._save_attribute_value(attribute_name=attribute_name)

    def _save_attribute_value(self, attribute_name: str):
        field_value = self._settings.__getattribute__(attribute_name)
        units_manager = app.activeProduct.unitsManager

        if type(field_value) is float:
            value_input: adsk.core.ValueCommandInput = self._attributes[attribute_name]
            value: float = units_manager.evaluateExpression(value_input.expression)
        elif type(field_value is int):
            value_input: adsk.core.ValueCommandInput = self._attributes[attribute_name]
            value: int = int(value_input.value)
        else:
            value_input: adsk.core.TextBoxCommandInput = self._attributes[
                attribute_name
            ]
            value: str = str(units_manager.value)

        self._settings.__setattr__(attribute_name, value)

    def _getPoint(self, theta, rMajor, rMinor, e, n):
        psi = math.atan2(
            math.sin((1 - n) * theta), ((rMajor / (e * n)) - math.cos((1 - n) * theta))
        )
        x = (
            (rMajor * math.cos(theta))
            - (rMinor * math.cos(theta + psi))
            - (e * math.cos(n * theta))
        )
        y = (
            (-rMajor * math.sin(theta))
            + (rMinor * math.sin(theta + psi))
            + (e * math.sin(n * theta))
        )
        return (x, y)

    def _distance(self, xa, ya, xb, yb):
        return math.hypot((xa - xb), (ya - yb))

    def _rotor(
        self,
        invert: bool,
        zOffset: float,
        name: str,
    ):
        newEccentricOffset = self._settings.eccentric_offset
        offsetAngle = 0
        if invert:
            newEccentricOffset *= -1
            offsetAngle = math.pi / self._settings.rotor_lobes

        rotorOcc = self._root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        rotor = rotorOcc.component
        rotor.name = name

        planes = rotor.constructionPlanes
        planeInput = planes.createInput()
        offsetValue = adsk.core.ValueInput.createByReal(zOffset)
        planeInput.setByOffset(self._root.xYConstructionPlane, offsetValue)
        constructionPlane = planes.add(planeInput)

        sk = rotor.sketches.add(constructionPlane)
        points = adsk.core.ObjectCollection.create()

        (xs, ys) = self._getPoint(
            0,
            self._settings.rotor_radius,
            self._settings.ring_gear_pin_radius,
            self._settings.eccentric_offset,
            self._settings.ring_gear_pins,
        )
        points.add(adsk.core.Point3D.create(xs, ys, 0))

        et = 2 * math.pi / self._settings.rotor_lobes
        (xe, ye) = self._getPoint(
            et,
            self._settings.rotor_radius,
            self._settings.ring_gear_pin_radius,
            self._settings.eccentric_offset,
            self._settings.ring_gear_pins,
        )
        x = xs
        y = ys
        dist = 0
        ct = 0
        dt = math.pi / self._settings.ring_gear_pins
        numPoints = 0

        while (
            self._distance(x, y, xe, ye) > self._settings.maximum_distance
            or ct < et / 2
        ) and ct < et:
            (xt, yt) = self._getPoint(
                ct + dt,
                self._settings.rotor_radius,
                self._settings.ring_gear_pin_radius,
                self._settings.eccentric_offset,
                self._settings.ring_gear_pins,
            )
            dist = self._distance(x, y, xt, yt)

            ddt = dt / 2
            lastTooBig = False
            lastTooSmall = False

            while (
                dist > self._settings.maximum_distance
                or dist < self._settings.minimum_distance
            ):
                if dist > self._settings.maximum_distance:
                    if lastTooSmall:
                        ddt /= 2

                    lastTooSmall = False
                    lastTooBig = True

                    if ddt > dt / 2:
                        ddt = dt / 2

                    dt -= ddt

                elif dist < self._settings.minimum_distance:
                    if lastTooBig:
                        ddt /= 2

                    lastTooSmall = True
                    lastTooBig = False
                    dt += ddt

                (xt, yt) = self._getPoint(
                    ct + dt,
                    self._settings.rotor_radius,
                    self._settings.ring_gear_pin_radius,
                    self._settings.eccentric_offset,
                    self._settings.ring_gear_pins,
                )
                dist = self._distance(x, y, xt, yt)

            x = xt
            y = yt
            points.add(adsk.core.Point3D.create(x, y, 0))
            numPoints += 1
            ct += dt

        points.add(adsk.core.Point3D.create(xe, ye, 0))
        curve = sk.sketchCurves.sketchFittedSplines.add(points)

        lines = sk.sketchCurves.sketchLines
        line1 = lines.addByTwoPoints(
            adsk.core.Point3D.create(0, 0, 0), curve.startSketchPoint
        )
        line2 = lines.addByTwoPoints(line1.startSketchPoint, curve.endSketchPoint)

        # Extrude
        prof = sk.profiles.item(0)
        # dist = adsk.core.ValueInput.createByReal(rotorThickness)
        dist = adsk.core.ValueInput.createByReal(self._settings.rotor_thickness)
        extrudes = rotor.features.extrudeFeatures
        extrude = extrudes.addSimple(
            prof, dist, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )

        # Create component
        body1 = extrude.bodies.item(0)
        body1.name = name
        inputEntities = adsk.core.ObjectCollection.create()
        inputEntities.add(body1)

        # Circular pattern
        zAxis = rotor.zConstructionAxis
        circularFeats = rotor.features.circularPatternFeatures
        circularFeatInput = circularFeats.createInput(inputEntities, zAxis)
        circularFeatInput.quantity = adsk.core.ValueInput.createByReal(
            self._settings.rotor_lobes
        )
        circularFeatInput.totalAngle = adsk.core.ValueInput.createByString("360 deg")
        circularFeatInput.isSymmetric = True
        circularFeat = circularFeats.add(circularFeatInput)

        # Combine pattern features
        ToolBodies = adsk.core.ObjectCollection.create()
        for b in circularFeat.bodies:
            if b != body1:
                ToolBodies.add(b)

        combineInput = rotor.features.combineFeatures.createInput(body1, ToolBodies)
        combineInput.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
        combineInput.isNewComponent = False
        rotor.features.combineFeatures.add(combineInput)

        # Center bearing hole
        sk = rotor.sketches.add(constructionPlane)
        sketchCircles = sk.sketchCurves.sketchCircles
        sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, 0, 0),
            self._settings.rotor_bearing_hole_diameter / 2,
        )

        prof = sk.profiles.item(0)
        # dist = adsk.core.ValueInput.createByReal(rotorThickness)
        dist = adsk.core.ValueInput.createByReal(self._settings.rotor_thickness)
        extrudes = rotor.features.extrudeFeatures
        extrude = extrudes.addSimple(
            prof, dist, adsk.fusion.FeatureOperations.CutFeatureOperation
        )

        # Output holes
        sk = rotor.sketches.add(constructionPlane)
        sketchCircles = sk.sketchCurves.sketchCircles
        sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(
                math.cos(-offsetAngle + math.pi / 2)
                * self._settings.output_circle_diameter
                / 2,
                math.sin(-offsetAngle + math.pi / 2)
                * self._settings.output_circle_diameter
                / 2,
                0,
            ),
            self._settings.output_hole_diameter / 2,
        )

        prof = sk.profiles.item(0)
        # dist = adsk.core.ValueInput.createByReal(rotorThickness)
        dist = adsk.core.ValueInput.createByReal(self._settings.rotor_thickness)
        extrudes = rotor.features.extrudeFeatures
        extrude = extrudes.addSimple(
            prof, dist, adsk.fusion.FeatureOperations.CutFeatureOperation
        )

        inputEntities = adsk.core.ObjectCollection.create()
        inputEntities.add(extrude)

        # Circular pattern
        circularFeats = rotor.features.circularPatternFeatures
        circularFeatInput = circularFeats.createInput(inputEntities, zAxis)
        circularFeatInput.quantity = adsk.core.ValueInput.createByReal(
            self._settings.output_hole_count
        )
        circularFeatInput.totalAngle = adsk.core.ValueInput.createByString("360 deg")
        circularFeatInput.isSymmetric = True
        circularFeat = circularFeats.add(circularFeatInput)

        # Offset the rotor to make the ring gear concentric with origin
        transform = rotorOcc.transform
        transform.setToRotation(
            offsetAngle,
            adsk.core.Vector3D.create(0, 0, 1),
            adsk.core.Point3D.create(0, 0, 0),
        )
        transform.translation = adsk.core.Vector3D.create(newEccentricOffset, 0, 0)
        rotorOcc.transform = transform
        self._design.snapshots.add()

    def _cam(
        self,
        invert: bool,
        zOffset: float,
        name: str,
    ):
        eccentric_offset: float = self._settings.eccentric_offset * (
            1 if not invert else -1
        )

        camshaftOcc = self._root.occurrences.addNewComponent(
            adsk.core.Matrix3D.create()
        )
        camshaft = camshaftOcc.component
        camshaft.name = name

        planes = camshaft.constructionPlanes
        plane_input = planes.createInput()
        offset_value = adsk.core.ValueInput.createByReal(zOffset)
        plane_input.setByOffset(self._root.xYConstructionPlane, offset_value)
        construction_plane = planes.add(plane_input)

        sk = camshaft.sketches.add(construction_plane)
        sketchCircles = sk.sketchCurves.sketchCircles
        sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(eccentric_offset, 0, 0),
            self._settings.camshaft_diameter / 2,
        )

        prof = sk.profiles.item(0)
        dist = adsk.core.ValueInput.createByReal(self._settings.rotor_thickness)
        extrudes = camshaft.features.extrudeFeatures
        extrude = extrudes.addSimple(
            prof, dist, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        extrude.bodies.item(0).name = name

    def _output_assembly(self, name: str):
        outputOcc = self._root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        output = outputOcc.component
        output.name = name

        # Output pins
        sk = output.sketches.add(self._root.xYConstructionPlane)
        sketchCircles = sk.sketchCurves.sketchCircles
        sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, self._settings.output_circle_diameter / 2, 0),
            self._settings.output_pin_diameter / 2,
        )

        prof = sk.profiles.item(0)
        dist = adsk.core.ValueInput.createByReal(self._settings.ring_gear_thickness)
        extrudes = output.features.extrudeFeatures
        extrude = extrudes.addSimple(
            prof, dist, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )

        inputEntities = adsk.core.ObjectCollection.create()
        inputEntities.add(extrude)

        # Circular pattern
        zAxis = output.zConstructionAxis
        circularFeats = output.features.circularPatternFeatures
        circularFeatInput = circularFeats.createInput(inputEntities, zAxis)
        circularFeatInput.quantity = adsk.core.ValueInput.createByReal(
            self._settings.output_hole_count
        )
        circularFeatInput.totalAngle = adsk.core.ValueInput.createByString("360 deg")
        circularFeatInput.isSymmetric = True
        circularFeat = circularFeats.add(circularFeatInput)

        # Output body
        planes = output.constructionPlanes
        planeInput = planes.createInput()
        offsetValue = adsk.core.ValueInput.createByReal(
            self._settings.ring_gear_thickness
        )
        planeInput.setByOffset(self._root.xYConstructionPlane, offsetValue)
        constructionPlane = planes.add(planeInput)

        sk = output.sketches.add(constructionPlane)
        sketchCircles = sk.sketchCurves.sketchCircles
        sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, 0, 0),
            self._settings.output_circle_diameter / 2
            + self._settings.output_pin_diameter,
        )

        prof = sk.profiles.item(0)
        dist = adsk.core.ValueInput.createByReal(self._settings.output_plate_thickness)
        extrudes = output.features.extrudeFeatures
        extrude = extrudes.addSimple(
            prof, dist, adsk.fusion.FeatureOperations.JoinFeatureOperation
        )
        extrude.bodies.item(0).name = name

    def _ring_gear(self, name: str):
        ringGearOcc = self._root.occurrences.addNewComponent(
            adsk.core.Matrix3D.create()
        )
        ringGear = ringGearOcc.component
        ringGear.name = name

        # Pins
        sk = ringGear.sketches.add(self._root.xYConstructionPlane)
        sketchCircles = sk.sketchCurves.sketchCircles
        centerPoint = adsk.core.Point3D.create(
            self._settings.rotor_radius + self._settings.ring_gear_margin, 0, 0
        )
        sketchCircles.addByCenterRadius(
            centerPoint, self._settings.ring_gear_pin_radius
        )

        prof = sk.profiles.item(0)
        dist = adsk.core.ValueInput.createByReal(self._settings.ring_gear_thickness)
        extrudes = ringGear.features.extrudeFeatures
        extrude = extrudes.addSimple(
            prof, dist, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )

        pin = extrude.bodies.item(0)
        pin.name = name
        inputEntities = adsk.core.ObjectCollection.create()
        inputEntities.add(pin)

        # Circular pattern
        zAxis = ringGear.zConstructionAxis
        circularFeats = ringGear.features.circularPatternFeatures
        circularFeatInput = circularFeats.createInput(inputEntities, zAxis)
        circularFeatInput.quantity = adsk.core.ValueInput.createByReal(
            self._settings.ring_gear_pins
        )
        circularFeatInput.totalAngle = adsk.core.ValueInput.createByString("360 deg")
        circularFeatInput.isSymmetric = True
        circularFeats.add(circularFeatInput)

        # Housing
        sk = ringGear.sketches.add(self._root.xYConstructionPlane)
        sketchCircles = sk.sketchCurves.sketchCircles
        sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, 0, 0),
            self._settings.rotor_radius + self._settings.ring_gear_margin,
        )
        sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, 0, 0),
            self._settings.ring_gear_outer_diameter / 2,
        )

        prof = sk.profiles.item(1)
        dist = adsk.core.ValueInput.createByReal(self._settings.ring_gear_thickness)
        extrudes = ringGear.features.extrudeFeatures
        extrude = extrudes.addSimple(
            prof, dist, adsk.fusion.FeatureOperations.JoinFeatureOperation
        )

        # Fillets - conditional fillet on edges with length matching gear thickness
        fillets = ringGear.features.filletFeatures

        edgeCollection1 = adsk.core.ObjectCollection.create()
        faces = ringGear.bRepBodies.item(0).faces
        for face in faces:
            for edge in face.edges:
                if abs(edge.length - self._settings.ring_gear_thickness) < 0.005:
                    edgeCollection1.add(edge)

        radius1 = adsk.core.ValueInput.createByReal(self._settings.ring_gear_pin_radius)
        input1 = fillets.createInput()
        input1.addConstantRadiusEdgeSet(edgeCollection1, radius1, True)
        input1.isG2 = False
        input1.isRollingBallCorner = True
        fillets.add(input1)

    def _draw_gear(self):
        try:
            self._rotor(
                invert=False, zOffset=self._settings.rotor_spacing, name="Rotor 1"
            )
            self._rotor(
                invert=True,
                zOffset=self._settings.rotor_thickness
                + (self._settings.rotor_spacing * 2),
                name="Rotor 2",
            )

            self._cam(
                invert=False,
                zOffset=self._settings.rotor_spacing,
                name="Camshaft 1",
            )
            self._cam(
                invert=True,
                zOffset=self._settings.rotor_thickness
                + (self._settings.rotor_spacing * 2),
                name="Camshaft 2",
            )

            self._output_assembly(name="Output")
            self._ring_gear(name="Ring Gear")

            return

        except:
            if ui:
                ui.messageBox(f"Failed:\n{format(traceback.format_exc())}")
