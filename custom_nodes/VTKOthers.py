from ..generated_nodes.gen_VTKTransform import *
from ..generated_nodes.gen_VTKImplicitFunc import *
from ..generated_nodes.gen_VTKParametricFunc import *
from ..generated_nodes.gen_VTKIntegrator import *
import mathutils
import math
from ..core import show_custom_code, run_custom_code

# --------------------------------------------------------------
# ImplicitFunctions base class
# --------------------------------------------------------------


class BVTK_ImplicitFunction:
    """Base class for implicit functions, which supports
    linking an object to. Inherited classes must implement:

    - new_object(self): Create a new object that can be linked
    - objects_list(self, context): Return an enum list of acceptable objects
    - object = bpy.props.EnumProperty(items=objects_list)
    Enum property that shows linkable objects (just copy&paste this)
    - properties_from_obj(self, ob): Update node m_props based on object
    position/rotation/etc. Called every second.
    """

    # DO NOT USE, TO BE REMOVED. This seems to conflict with the new
    # update system introduced in core_refactor branch.

    # TODO: Seems to contain stuff similar to core.py BVTK_Node, check
    # if can be inherited.

    def set_wire(self, value):
        """Set drawing style to wire mode"""
        if self.object in bpy.data.objects:
            if value:
                bpy.data.objects[self.object].display_type = "WIRE"
            else:
                bpy.data.objects[self.object].display_type = "SOLID"

    def is_wire(self):
        """Check if drawing style is wire mode"""
        if self.object in bpy.data.objects:
            return bpy.data.objects[self.object].display_type == "WIRE"
        return False

    draw_wire: bpy.props.BoolProperty(set=set_wire, get=is_wire)

    # TODO: decipher and rewrite comment:
    # useful for not transparent objects,
    # set max draw type to wire. Set a variable
    # 'use_wire' in inherited class to use this.

    def unlink_object(self):
        self.using_object = False

    def update_object(self, context):
        if self.using_object:
            self.link_object()

    using_object: bpy.props.BoolProperty(
        default=False,
        update=update_object,
        description="Get Normal and Origin from Blender Object",
    )

    def link_object(self):
        """Link object to node"""
        name = self.object
        if name in bpy.data.objects:
            ob = bpy.data.objects[name]
        else:
            self.new_object()
            ob = bpy.context.active_object
        bpy.ops.node.bvtk_link_object(object_name=ob.name, node_path=node_path(self))
        self.object = ob.name

    def draw_buttons_special(self, context, layout):
        # Options to get orientation from a Blender Object
        row = layout.row(align=True)
        row.label(text="Orientation Object:")
        row = layout.row(align=True)
        row2 = row.row(align=True)
        row2.enabled = not self.using_object
        row2.prop(self, "object", text="")
        if self.using_object and hasattr(self, "use_wire"):
            row.prop(self, "draw_wire", text="", icon="MOD_WIREFRAME", toggle=True)
        text = "Unlink Object" if self.using_object else "Link Object"
        row.prop(self, "using_object", text=text, toggle=True)

        # Show properties
        m_properties = self.m_properties()
        for i in range(len(m_properties)):
            if self.b_properties[i]:
                row = layout.row()
                row.enabled = not self.using_object
                row.prop(self, m_properties[i])

    def apply_properties_special(self):
        vtk_obj = self.get_vtk_obj()
        if self.using_object and self.object in bpy.data.objects:
            self.properties_from_obj(bpy.data.objects[self.object])
        m_properties = self.m_properties()
        for x in [
            m_properties[i] for i in range(len(m_properties)) if self.b_properties[i]
        ]:
            # SetXFileName(Y)
            if "FileName" in x:
                value = os.path.realpath(bpy.path.abspath(getattr(self, x)))
                cmd = "vtk_obj.Set" + x[2:] + "(value)"
            # SetXToY()
            elif x.startswith("e_"):
                value = getattr(self, x)
                cmd = "vtk_obj.Set" + x[2:] + "To" + value + "()"
            # SetX(self.Y)
            else:
                cmd = "vtk_obj.Set" + x[2:] + "(self." + x + ")"
            # TODO: Error handling
            exec(cmd, globals(), locals())
        return "up-to-date"


class BVTK_OT_LinkObject(bpy.types.Operator):
    """Operator to assign properties from linked object at 1 s interval"""

    # DO NOT USE, TO BE REMOVED. This seems to conflict with the new
    # update system introduced in core_refactor branch.

    # Usage example: Connect a VTKPlane node with a plane object
    # or an empty. Sets m_Normal and m_Origin of the node
    # using location and rotation of the plane

    bl_idname = "node.bvtk_link_object"
    bl_label = "Connect object and node"

    _timer = None
    object_name: bpy.props.StringProperty()  # name of the object to connect
    node_path: bpy.props.StringProperty()  # path of the node to connect

    def node_is_valid(self):
        """return false if node has been deleted or link has been turned off"""
        return self.node.name and self.node.using_object

    def ob_is_valid(self):
        """return false if object has been deleted"""
        return self.object.name in bpy.data.objects

    def modal(self, context, event):
        if event.type == "TIMER":
            node_is_valid = self.node_is_valid()
            if self.ob_is_valid():
                if node_is_valid:
                    self.node.properties_from_obj(self.object)
                    return {"PASS_THROUGH"}
            else:
                if node_is_valid:
                    self.node.unlink_object()
            return self.cancel(context)
        return {"PASS_THROUGH"}

    def execute(self, context):
        self.object = bpy.data.objects[self.object_name]
        self.node = eval(self.node_path)
        wm = context.window_manager
        self._timer = wm.event_timer_add(1, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        return {"CANCELLED"}


add_ui_class(BVTK_OT_LinkObject)

# --------------------------------------------------------------


class VTKPlane(Node, BVTK_Node):
    """Customized VTK Plane, optionally get orientation from a Blender object"""

    bl_idname = "VTKPlaneType"
    bl_label = "vtkPlane"

    m_Normal: bpy.props.FloatVectorProperty(
        name="Normal",
        default=[0.0, 0.0, 1.0],
        size=3,
        update=BVTK_Node.outdate_vtk_status,
    )
    m_Origin: bpy.props.FloatVectorProperty(
        name="Origin",
        default=[0.0, 0.0, 0.0],
        size=3,
        update=BVTK_Node.outdate_vtk_status,
    )
    orientation_object: bpy.props.StringProperty(
        default="", name="Orientation Object", update=BVTK_Node.outdate_vtk_status
    )

    b_properties: bpy.props.BoolVectorProperty(
        name="", size=3, get=BVTK_Node.get_b, set=BVTK_Node.set_b
    )

    def m_properties(self):
        return ["m_Normal", "m_Origin", "orientation_object"]

    def m_connections(self):
        return ([], [], ["Transform"], ["output"])

    def orientation_object_enum_generator(self, context=None):
        """Return all planes and empties names. Mesh object is considered a
        plane if it has 4 vertices.
        """
        items = [("None", "Empty (clear value)", "Empty (clear value)", ENUM_ICON, 0)]
        i = 1
        for ob in bpy.data.objects:
            if ob.type == "EMPTY":
                items.append((ob.name, ob.name, ob.name, "OUTLINER_OB_EMPTY", i))
                i += 1
            elif hasattr(ob.data, "vertices") and len(ob.data.vertices) == 4:
                items.append((ob.name, ob.name, ob.name, "MESH_PLANE", i))
                i += 1
        return items

    def orientation_object_set_value(self, context=None):
        """Set value of StringProprety using value from EnumProperty"""
        if self.orientation_object_enum == "None":
            self.orientation_object = ""
        else:
            self.orientation_object = str(self.orientation_object_enum)

    orientation_object_enum: bpy.props.EnumProperty(
        items=orientation_object_enum_generator,
        update=orientation_object_set_value,
        name="Choices",
    )

    def validate_and_update_values_special(self):
        """Check that provided orientation information has no issues.
        """
        # If there's no object name, use normal and origin from node values.
        # Otherwise specified object needs to exist.
        if len(self.orientation_object) < 1:
            return None
        orientation_object_enum_list = first_elements(
            self.orientation_object_enum_generator()
        )
        if not self.orientation_object in orientation_object_enum_list:
            return (
                "No Blender object %r (must be an Empty or a Plane)"
                % self.orientation_object
            )

    def draw_buttons_special(self, context, layout):
        row = layout.row(align=True)
        row.prop(self, "orientation_object")
        row.prop(self, "orientation_object_enum", icon_only=True)
        row = layout.row(align=True)
        row.prop(self, "m_Origin")
        row = layout.row(align=True)
        row.prop(self, "m_Normal")

    def properties_from_obj(self, ob):
        """Set origin and normal from a Blender object.
        """
        mat = ob.matrix_world
        if ob.data:  # if it has data it's not an empty
            mesh = ob.data.copy()
            mesh.transform(mat)
            face = mesh.polygons[0]
            self.m_Normal = face.normal
            self.m_Origin = face.center
        else:
            loc, rot, sca = mat.decompose()
            v = mathutils.Vector((0, 0, 1))
            self.m_Normal = rot @ v
            self.m_Origin = ob.location

    def apply_properties_special(self):
        # Update values from orientation object if needed.
        if len(self.orientation_object) > 0:
            ob = bpy.data.objects[self.orientation_object]
            self.properties_from_obj(ob)

        # Set origin and normal
        vtk_obj = self.get_vtk_obj()
        vtk_obj.SetOrigin(self.m_Origin)
        vtk_obj.SetNormal(self.m_Normal)
        return "up-to-date"

    def init_vtk(self):
        self.set_vtk_status("out-of-date")
        vtk_obj = vtk.vtkPlane()
        return vtk_obj


add_class(VTKPlane)

# --------------------------------------------------------------


class VTKSphere(BVTK_ImplicitFunction, Node, BVTK_Node):
    """Manually modified version VTK Sphere"""

    bl_idname = "VTKSphereType"
    bl_label = "vtkSphere"

    m_Radius: bpy.props.FloatProperty(name="Radius", default=0.5)
    m_Center: bpy.props.FloatVectorProperty(
        name="Center", default=[0.0, 0.0, 0.0], size=3
    )

    b_properties: bpy.props.BoolVectorProperty(
        name="", size=2, get=BVTK_Node.get_b, set=BVTK_Node.set_b
    )

    def m_properties(self):
        return [
            "m_Radius",
            "m_Center",
        ]

    def m_connections(self):
        return ([], [], ["Transform"], ["self"])

    def new_object(self):
        bpy.ops.object.empty_add(type="SPHERE", radius=2.0)

    def objects_list(self, context):
        """ Return all sphere empties names """
        items = []
        objects = bpy.data.objects
        i = 0
        for ob in objects:
            if ob.type == "EMPTY":
                if ob.empty_draw_type == "SPHERE":
                    items.append((ob.name, ob.name, ob.name, "OUTLINER_OB_EMPTY", i))
                    i += 1
        items.append(("New sphere", "New sphere", "New sphere", "", i))
        useless_list[self.name] = items
        return items

    object: bpy.props.EnumProperty(items=objects_list)

    def properties_from_obj(self, ob):
        self.m_Radius = ob.empty_draw_size * ob.scale[0]  # assuming scale x = y = z
        self.m_Center = ob.location


# TODO: Upgrade customized version (supporting location and scale from
# Blender Sphere Empty object). Similar implementation as for vtkPlane.
# add_class(VTKSphere)
