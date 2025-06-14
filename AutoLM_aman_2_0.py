bl_info = {
    "name": "AutoLM by Aman 2.0",
    "author": "Aman",
    "version": (2, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > AutoLM_Aman 2.0 (N Panel)",
    "description": "Create and manage dot labels with animation data export (Blender 4.0+) - Version 2.0",
    "category": "Add-ons",
    "support": "COMMUNITY",
    "doc_url": "https://github.com/yourusername/AutoLM_aman_2_0",  # Replace with your GitHub repo URL
    "tracker_url": "https://github.com/yourusername/AutoLM_aman_2_0/issues",  # Replace with your issues URL
    "update_url": "https://raw.githubusercontent.com/yourusername/AutoLM_aman_2_0/main/version.json"  # Replace with your version info URL
}

# Module name for Blender
__module_name__ = "AutoLM_aman_2_0"

import bpy
import os
import pathlib
import re
from mathutils import Vector
import bpy.props
import blf
import bpy_extras
from bpy.app import version as blender_version
from difflib import SequenceMatcher
import json
from collections import defaultdict
import urllib.request
from urllib.error import URLError

def check_for_update():
    """Check if a new version is available"""
    try:
        if not bl_info.get('update_url'):
            return None, None
            
        with urllib.request.urlopen(bl_info['update_url']) as response:
            data = json.loads(response.read())
            latest_version = tuple(data.get('version', [0, 0]))
            download_url = data.get('download_url', '')
            
            if latest_version > bl_info['version']:
                return latest_version, download_url
    except (URLError, json.JSONDecodeError):
        pass
    return None, None

# List to hold drawing handlers
_draw_handlers = []

class AutoLM_UpdatePanel(bpy.types.Panel):
    bl_label = "Updates"
    bl_idname = "VIEW3D_PT_autolm_update"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'AutoLM_Aman 2.0'
    bl_order = 0
    
    @classmethod
    def poll(cls, context):
        latest_version, _ = check_for_update()
        return latest_version is not None
    
    def draw(self, context):
        layout = self.layout
        latest_version, download_url = check_for_update()
        
        if latest_version:
            version_str = '.'.join(str(v) for v in latest_version)
            layout.label(text=f"New version {version_str} available!")
            if download_url:
                layout.operator("wm.url_open", text="Download Update").url = download_url
            layout.operator("wm.url_open", text="View Documentation").url = bl_info['doc_url']

class DescriptionSuggester:
    def __init__(self):
        self.word_frequencies = defaultdict(int)
        self.common_mistakes = defaultdict(list)
        self.load_data()
        
        # Add a default set of science-related words
        self.add_default_science_words()
    
    def add_default_science_words(self):
        """Load default science-related words from a JSON file."""
        try:
            script_dir = os.path.dirname(__file__)
            science_words_path = os.path.join(script_dir, "wordlist.json")
            if os.path.exists(science_words_path):
                with open(science_words_path, 'r', encoding='utf-8') as f:
                    science_words = json.load(f)
                for word in science_words:
                    self.add_description(word)
                print(f"Loaded {len(science_words)} default science words from {science_words_path}")
            else:
                print(f"Warning: {science_words_path} not found. No default science words loaded.")
        except Exception as e:
            print(f"Error loading default science words: {e}")
    
    def load_data(self):
        """Load saved word frequencies and common mistakes"""
        try:
            if os.path.exists("description_data.json"):
                with open("description_data.json", 'r') as f:
                    data = json.load(f)
                    self.word_frequencies = defaultdict(int, data.get('frequencies', {}))
                    self.common_mistakes = defaultdict(list, data.get('mistakes', {}))
        except Exception as e:
            print(f"Error loading description data: {e}")
    
    def save_data(self):
        """Save word frequencies and common mistakes"""
        try:
            data = {
                'frequencies': dict(self.word_frequencies),
                'mistakes': dict(self.common_mistakes)
            }
            with open("description_data.json", 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error saving description data: {e}")
    
    def add_description(self, description):
        """Add a new description to learn from"""
        words = description.lower().split()
        for word in words:
            self.word_frequencies[word] += 1
    
    def get_similarity(self, word1, word2):
        """Get similarity ratio between two words"""
        return SequenceMatcher(None, word1.lower(), word2.lower()).ratio()
    
    def find_similar_words(self, word, threshold=0.8):
        """Find similar words from known words"""
        similar_words = []
        for known_word in self.word_frequencies.keys():
            if self.get_similarity(word, known_word) > threshold:
                similar_words.append((known_word, self.word_frequencies[known_word]))
        return sorted(similar_words, key=lambda x: x[1], reverse=True)
    
    def check_description(self, description):
        """Check description and return suggestions"""
        words = description.lower().split()
        suggestions = []
        
        for word in words:
            # Skip very short words
            if len(word) <= 2:
                continue
                
            # If word is not in our known words
            if word not in self.word_frequencies:
                similar_words = self.find_similar_words(word)
                if similar_words:
                    suggestions.append({
                        'word': word,
                        'suggestions': [w[0] for w in similar_words[:3]]  # Top 3 suggestions
                    })
        
        return suggestions

# Create global suggester instance
description_suggester = DescriptionSuggester()

def create_transparent_material(name):
    # Check if the material already exists
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    
    # Get the Principled BSDF node
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        # Set only the essential properties for transparency
        bsdf.inputs["Alpha"].default_value = 0.0
        bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    
    # Enable transparency in material settings
    mat.blend_method = 'BLEND'
    mat.use_backface_culling = False
    
    return mat

def get_next_label_number():
    max_num = 0
    for obj in bpy.data.objects:
        if obj.name.startswith("dot-") or obj.name.startswith("label-"):
            try:
                num = int(obj.name.split("-")[-1])
                max_num = max(max_num, num)
            except ValueError:
                continue
    return max_num + 1

class DOT_OT_create_label(bpy.types.Operator):
    bl_idname = "dot.create_label"
    bl_label = "Create New Label"
    bl_description = "Creates a new dot label at 3D cursor or replaces selected object"

    # Add properties for user input
    label_object_name: bpy.props.StringProperty(
        name="Label Object Name",
        default="",
        description="Name for the label object (e.g., label-001)"
    )
    label_mesh_name: bpy.props.StringProperty(
        name="Label Mesh Name",
        default="",
        description="Name for the label mesh data (e.g., Cube.label)"
    )
    dot_object_name: bpy.props.StringProperty(
        name="Dot Object Name",
        default="",
        description="Name for the dot object (e.g., dot-001)"
    )
    dot_mesh_name: bpy.props.StringProperty(
        name="Dot Mesh Name",
        default="",
        description="Name for the dot mesh data (e.g., Sphere.dot)"
    )
    description: bpy.props.StringProperty(
        name="Description",
        default="",
        description="Description for this label (will be stored in GLB)"
    )
    animdata: bpy.props.StringProperty(
        name="Animation Data",
        default="",
        description="Additional animation data description (will be stored in GLB)"
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        try:
            # Create base meshes
            bpy.ops.mesh.primitive_cube_add(size=0.01)
            base_cube = bpy.context.object
            # Assign mesh name before copying
            if self.label_mesh_name:
                base_cube.data.name = self.label_mesh_name
            else:
                base_cube.data.name = "Cube.label.mesh"
            cube_mesh = base_cube.data.copy()
            bpy.data.objects.remove(base_cube)

            # Replace cone with Icosphere (lowest tris)
            bpy.ops.mesh.primitive_ico_sphere_add(radius=0.01, subdivisions=1)
            base_cone = bpy.context.object
            # Assign mesh name before copying
            if self.dot_mesh_name:
                base_cone.data.name = self.dot_mesh_name
            else:
                base_cone.data.name = "Icosphere.dot.mesh"
            cone_mesh = base_cone.data.copy()
            bpy.data.objects.remove(base_cone)

            # Create transparent material
            transparent_mat = create_transparent_material("Dot_Transparent_Mat")

            # Get location and rotation and determine object names
            loc = context.scene.cursor.location.copy()
            rot = (0, 0, 0)
            label_obj_name = self.label_object_name
            dot_obj_name = self.dot_object_name

            if context.selected_objects:
                obj = context.selected_objects[0]
                loc = obj.location.copy()
                rot = obj.rotation_euler.copy()
                # If object names not provided, try to get number from original object name
                if not label_obj_name or not dot_obj_name:
                    match = re.search(r"dot\.(\d+)", obj.name)
                    if match:
                        num = match.group(1)
                        if not label_obj_name:
                            label_obj_name = f"label-{num.zfill(3)}"
                        if not dot_obj_name:
                            dot_obj_name = f"dot-{num.zfill(3)}"
                    else:
                        # Fallback to sequential if no dot.XX pattern
                        if not label_obj_name:
                            label_obj_name = f"label-{str(get_next_label_number()).zfill(3)}"
                        if not dot_obj_name:
                            dot_obj_name = f"dot-{str(get_next_label_number()).zfill(3)}"
                # Remove original object
                bpy.data.objects.remove(obj, do_unlink=True)
            else:
                # If no object selected and names not provided, use sequential
                if not label_obj_name:
                    label_obj_name = f"label-{str(get_next_label_number()).zfill(3)}"
                if not dot_obj_name:
                    dot_obj_name = f"dot-{str(get_next_label_number()).zfill(3)}"

            # Create label cube
            label_obj = bpy.data.objects.new(label_obj_name, cube_mesh)
            label_obj.location = loc
            label_obj.rotation_euler = rot
            label_obj.scale = (0.01, 0.01, 0.01)
            context.collection.objects.link(label_obj)
            label_obj.data.materials.append(transparent_mat)
            # Make label object visible in viewport
            label_obj.display_type = 'WIRE'
            label_obj.show_all_edges = True
            label_obj.show_wire = True
            # Show object name in viewport
            label_obj.show_name = True
            # Store description using built-in property system
            if self.description or self.animdata:
                label_obj["dot_label_data"] = {
                    "description": self.description,
                    "animdata": self.animdata
                }

            # Create dot sphere
            dot_obj = bpy.data.objects.new(dot_obj_name, cone_mesh)
            dot_obj.location = loc
            dot_obj.rotation_euler = rot
            dot_obj.scale = (0.01, 0.01, 0.01)
            context.collection.objects.link(dot_obj)
            dot_obj.data.materials.append(transparent_mat)
            # Show object name in viewport
            dot_obj.show_name = True
            # Store description using built-in property system
            if self.description or self.animdata:
                dot_obj["dot_label_data"] = {
                    "description": self.description,
                    "animdata": self.animdata
                }

            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error creating label: {str(e)}")
            return {'CANCELLED'}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "label_object_name")
        layout.prop(self, "label_mesh_name")
        layout.prop(self, "dot_object_name")
        layout.prop(self, "dot_mesh_name")
        layout.prop(self, "description")
        layout.prop(self, "animdata")

class DOT_OT_export_data(bpy.types.Operator):
    bl_idname = "dot.export_data"
    bl_label = "Export Label Data"
    bl_description = "Exports dot label data to HTML"

    def execute(self, context):
        try:
            # First, collect all descriptions for training
            print("\n--- Starting description collection for training ---")
            for obj in bpy.data.objects:
                if obj.name.startswith("label-") or obj.name.startswith("dot-"):
                    # Check for dot_label_data custom property
                    if "dot_label_data" in obj:
                        description = obj["dot_label_data"].get("description", "")
                        if description:
                            print(f"Found description in {obj.name}: {description}")
                            description_suggester.add_description(description)
                    
                    # Also check for any other custom properties that might contain descriptions
                    for prop in obj.keys():
                        if prop != "dot_label_data" and isinstance(obj[prop], (str, dict)):
                            if isinstance(obj[prop], str):
                                print(f"Found string property in {obj.name}.{prop}: {obj[prop]}")
                                description_suggester.add_description(obj[prop])
                            elif isinstance(obj[prop], dict):
                                for key, value in obj[prop].items():
                                    if isinstance(value, str):
                                        print(f"Found string in {obj.name}.{prop}.{key}: {value}")
                                        description_suggester.add_description(value)
            
            # Save the updated dictionary
            description_suggester.save_data()
            print("--- Finished description collection and training ---\n")

            html = """<!DOCTYPE html>
<html>
<head>
    <title>Dot Label Data Export</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #eee;
            padding-bottom: 10px;
        }
        .label-group {
            margin: 15px 0;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 4px;
            background-color: #fff;
        }
        .label-number {
            font-size: 1.2em;
            color: #2c3e50;
            margin-bottom: 10px;
        }
        .label-details {
            margin-left: 20px;
        }
        .label-item {
            margin: 10px 0;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 4px;
        }
        .label-name {
            font-weight: bold;
            color: #2c3e50;
        }
        .mesh-name {
            color: #666;
            font-style: italic;
        }
        .description {
            color: #34495e;
            margin-top: 5px;
        }
        .anim-data {
            color: #27ae60;
            margin-top: 5px;
        }
        .no-data {
            color: #95a5a6;
            font-style: italic;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Dot Label Data Export</h1>
        <div class="label-groups">"""

            # Group objects by their number
            label_groups = {}
            for obj in bpy.data.objects:
                if obj.name.startswith("dot-") or obj.name.startswith("label-"):
                    parts = obj.name.split("-")
                    if len(parts) > 1:
                        num = parts[-1]
                        if num.isdigit():  # Ensure the suffix is a number
                            if num not in label_groups:
                                label_groups[num] = {"dot": None, "label": None}
                            if obj.name.startswith("dot-"):
                                label_groups[num]["dot"] = obj
                            else:
                                label_groups[num]["label"] = obj

            # Process each group
            for num in sorted(label_groups.keys()):
                group = label_groups[num]
                dot_obj = group.get("dot")
                label_obj = group.get("label")

                html += f"""
            <div class="label-group">
                <div class="label-number">Label Group {num}</div>
                <div class="label-details">"""

                if label_obj:
                    label_mesh_data_name = label_obj.data.name if label_obj.data else "No Mesh Data"
                    description = "No description"
                    animdata = "No animation data"
                    if "dot_label_data" in label_obj:
                        description = label_obj["dot_label_data"].get("description", "No description")
                        animdata = label_obj["dot_label_data"].get("animdata", "No animation data")
                    
                    html += f"""
                    <div class="label-item">
                        <div class="label-name">Label: {label_obj.name}</div>
                        <div class="mesh-name">Mesh: {label_mesh_data_name}</div>
                        <div class="description">Description: {description}</div>
                        <div class="anim-data">Animation Data: {animdata}</div>
                    </div>"""

                if dot_obj:
                    animation_info = "No animation"
                    if dot_obj.animation_data and dot_obj.animation_data.action:
                        action = dot_obj.animation_data.action
                        fcurves = [fc for fc in action.fcurves if fc.data_path == "scale"]
                        keyframes = set()
                        for fc in fcurves:
                            for key in fc.keyframe_points:
                                keyframes.add(int(key.co.x))
                        if keyframes:
                            animation_info = f"Keyframes at frames: {sorted(keyframes)}"
                    
                    html += f"""
                    <div class="label-item">
                        <div class="label-name">Dot: {dot_obj.name}</div>
                        <div class="anim-data">Animation: {animation_info}</div>
                    </div>"""

                html += """
                </div>
            </div>"""

            html += """
        </div>
    </div>
</body>
</html>"""

            # Get the blend file path
            blend_file_path = bpy.data.filepath
            if not blend_file_path:
                self.report({'ERROR'}, "Please save your blend file first")
                return {'CANCELLED'}

            # Create the HTML and JSON file paths
            html_path = os.path.splitext(blend_file_path)[0] + "_dot_labels.html"
            json_path = os.path.splitext(blend_file_path)[0] + "_dot_labels.json"

            # Write the HTML file
            with open(html_path, 'w') as f:
                f.write(html)

            # Create JSON data
            json_data = []
            for num in sorted(label_groups.keys()):
                group = label_groups[num]
                label_obj = group.get("label")
                if label_obj and "dot_label_data" in label_obj:
                    data = label_obj["dot_label_data"]
                    description = data.get("description", "")
                    animdata = data.get("animdata", "")
                    
                    # Parse animation data
                    first_value = 32
                    second_value = 160
                    if animdata:
                        parts = animdata.split("-")
                        if len(parts) == 2:
                            try:
                                first_value = int(parts[0])
                                second_value = int(parts[1])
                            except ValueError:
                                pass

                    label_entry = {
                        "text": [
                            {
                                "text": description,
                                "lang": "en"
                            }
                        ],
                        "isAnimation": True,
                        "animation": {
                            "frame": {
                                "first_value": first_value,
                                "second_value": second_value
                            }
                        }
                    }
                    json_data.append(label_entry)

            # Write the JSON file
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=4, ensure_ascii=False)

            self.report({'INFO'}, f"Exported dot label data to HTML and JSON: {html_path}, {json_path}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error exporting data: {str(e)}")
            return {'CANCELLED'}

class DOT_OT_edit_properties(bpy.types.Operator):
    bl_idname = "dot.edit_properties"
    bl_label = "Edit Properties"
    bl_description = "Edit properties of the selected dot/label object"

    description: bpy.props.StringProperty(
        name="Description",
        default="",
        description="Description for this label"
    )
    animdata: bpy.props.StringProperty(
        name="Animation Data",
        default="",
        description="Additional animation data description"
    )
    mesh_name: bpy.props.StringProperty(
        name="Mesh Name",
        default="",
        description="Name for the mesh data"
    )

    def invoke(self, context, event):
        obj = context.active_object
        if obj:
            if "dot_label_data" in obj:
                self.description = obj["dot_label_data"].get("description", "")
                self.animdata = obj["dot_label_data"].get("animdata", "")
            if obj.data:
                self.mesh_name = obj.data.name
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "No active object selected")
            return {'CANCELLED'}

        if not obj.name.startswith("dot-") and not obj.name.startswith("label-"):
            self.report({'ERROR'}, "Selected object is not a dot or label")
            return {'CANCELLED'}

        # Update the properties
        obj["dot_label_data"] = {
            "description": self.description,
            "animdata": self.animdata
        }

        # Update mesh name if provided
        if self.mesh_name and obj.data:
            obj.data.name = self.mesh_name

        return {'FINISHED'}

class DOT_OT_shift_animation(bpy.types.Operator):
    bl_idname = "dot.shift_animation"
    bl_label = "Shift Animation Data"
    bl_description = "Shift all dot label animation data by specified frames"

    frame_offset: bpy.props.IntProperty(
        name="Frame Offset",
        default=0,
        description="Number of frames to shift animation data (positive = forward, negative = backward)"
    )

    def execute(self, context):
        try:
            # Get all objects that might have dot_label_data
            objects = [obj for obj in bpy.data.objects if obj.name.startswith("dot-") or obj.name.startswith("label-")]
            
            for obj in objects:
                if "dot_label_data" in obj:
                    # Get the current data
                    current_data = obj["dot_label_data"]
                    
                    # Create a new dictionary to store the updated data
                    new_data = {
                        "description": current_data.get("description", ""),
                        "animdata": current_data.get("animdata", "")
                    }
                    
                    # Update the animdata if it exists and is in the correct format
                    if new_data["animdata"]:
                        parts = new_data["animdata"].split("-")
                        if len(parts) == 2:
                            try:
                                start_frame = int(parts[0])
                                end_frame = int(parts[1])
                                
                                new_start_frame = start_frame + self.frame_offset
                                new_end_frame = end_frame + self.frame_offset
                                
                                new_data["animdata"] = f"{new_start_frame}-{new_end_frame}"
                            except ValueError:
                                # If parsing fails, keep original data
                                pass # Do nothing, retain original value
                        else:
                            # If not in "start-end" format, keep original
                            pass # Do nothing, retain original value
                    
                    # Update the object's property with the new data
                    obj["dot_label_data"] = new_data
                    obj.update_tag()
            
            # Force a redraw of the viewport and properties editor
            for area in context.screen.areas:
                if area.type == 'VIEW_3D' or area.type == 'PROPERTIES': # Also redraw properties editor
                    area.tag_redraw()
            
            self.report({'INFO'}, f"Shifted animation data by {self.frame_offset} frames for existing labels.")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error shifting animation data: {str(e)}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "frame_offset")

class DOT_OT_add_timeline_markers(bpy.types.Operator):
    bl_idname = "dot.add_timeline_markers"
    bl_label = "Add Timeline Markers"
    bl_description = "Adds timeline markers based on label animation data"

    def execute(self, context):
        try:
            scene = context.scene
            # Clear existing markers related to our labels to avoid duplicates
            markers_to_remove = []
            for marker in scene.timeline_markers:
                if marker.name.endswith("_start") or marker.name.endswith("_end"): # Only remove markers we created
                    markers_to_remove.append(marker)
            for marker in markers_to_remove:
                scene.timeline_markers.remove(marker)

            for obj in bpy.data.objects:
                if obj.name.startswith("label-"):
                    if "dot_label_data" in obj:
                        animdata = obj["dot_label_data"].get("animdata", "")
                        if animdata:
                            parts = animdata.split("-")
                            if len(parts) == 2:
                                try:
                                    start_frame = int(parts[0])
                                    end_frame = int(parts[1])
                                    
                                    # Get the description for the marker name
                                    description = obj["dot_label_data"].get("description", "")
                                    marker_base_name = obj.name
                                    if description:
                                        # Replace spaces with underscores for cleaner marker names
                                        clean_description = description.replace(" ", "_")
                                        marker_base_name = f"{obj.name}_{clean_description}"

                                    # Add START marker
                                    start_marker = scene.timeline_markers.new(f"{marker_base_name}_start", frame=start_frame)
                                    start_marker["dot_label_name"] = obj.name # Store original label name
                                    
                                    # Add END marker
                                    end_marker = scene.timeline_markers.new(f"{marker_base_name}_end", frame=end_frame)
                                    end_marker["dot_label_name"] = obj.name # Store original label name

                                    self.report({'INFO'}, f"Added markers for {obj.name}: Start {start_frame}, End {end_frame}")
                                except ValueError:
                                    self.report({'WARNING'}, f"Could not parse animdata for {obj.name}: {animdata}")

            self.report({'INFO'}, "Timeline markers added successfully!")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error adding timeline markers: {str(e)}")
            return {'CANCELLED'}

class DOT_OT_sync_markers_to_data(bpy.types.Operator):
    bl_idname = "dot.sync_markers_to_data"
    bl_label = "Sync Markers to Data"
    bl_description = "Reads timeline marker positions and updates label animation data"

    def execute(self, context):
        try:
            scene = context.scene
            updated_labels = {}

            # Collect all relevant markers
            markers = {}
            print("\n--- Sync Markers to Data: Starting collection of markers ---")
            for marker in scene.timeline_markers:
                if "dot_label_name" in marker and (marker.name.endswith("_start") or marker.name.endswith("_end")):
                    label_name = marker["dot_label_name"]
                    print(f"Found marker: {marker.name} at frame {marker.frame}, linked to label: {label_name}")
                    if label_name not in markers:
                        markers[label_name] = {"start": None, "end": None}
                    
                    if marker.name.endswith("_start"):
                        markers[label_name]["start"] = marker
                    elif marker.name.endswith("_end"):
                        markers[label_name]["end"] = marker
            print(f"Finished collecting markers. Found {len(markers)} label groups.")

            print("\n--- Sync Markers to Data: Processing label data ---")
            for label_name, marker_pair in markers.items():
                obj = bpy.data.objects.get(label_name)
                print(f"Processing label: {label_name}")
                if obj:
                    print(f"  Label object found: {obj.name}")
                    if "dot_label_data" in obj:
                        if marker_pair["start"] and marker_pair["end"]:
                            new_start_frame = int(marker_pair["start"].frame)
                            new_end_frame = int(marker_pair["end"].frame)
                            
                            current_data = dict(obj["dot_label_data"])
                            old_animdata_string = current_data.get("animdata")
                            new_animdata_string = f"{new_start_frame}-{new_end_frame}"
                            
                            print(f"    Current animdata in property: '{old_animdata_string}'")
                            print(f"    New animdata from markers:  '{new_animdata_string}'")

                            if old_animdata_string != new_animdata_string:
                                current_data["animdata"] = new_animdata_string
                                obj["dot_label_data"] = current_data
                                obj.update_tag()
                                updated_labels[label_name] = True
                                print(f"    *** UPDATED animdata for {label_name} to: '{new_animdata_string}' ***")
                            else:
                                print(f"    Animdata for {label_name} is already up to date. No change needed.")
                        else:
                            print(f"    Warning: Missing start or end marker for {label_name}. Cannot sync.")
                    else:
                        print(f"    Warning: 'dot_label_data' custom property not found on {obj.name}. Skipping.")
                else:
                    print(f"  Label object '{label_name}' not found in bpy.data.objects. Skipping.")
            
            # Force a redraw of the viewport to show property updates
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

            if updated_labels:
                self.report({'INFO'}, f"Synced animation data for {len(updated_labels)} labels from markers.")
            else:
                self.report({'INFO'}, "No label animation data needed updating from markers.")
            print("--- Sync Markers to Data: Finished ---")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error syncing markers to data: {str(e)}")
            print(f"Error during Sync Markers to Data: {str(e)}") # Also print to console
            return {'CANCELLED'}

class DOT_PT_label_panel(bpy.types.Panel):
    bl_label = "AutoLM by Aman 2.0"
    bl_idname = "DOT_PT_label_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'AutoLM_Aman 2.0'

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        # Create label button
        layout.operator("dot.create_label")
        
        # Property management section
        if obj and (obj.name.startswith("dot-") or obj.name.startswith("label-")):
            box = layout.box()
            box.label(text="Properties")
            
            # Show current properties
            if "dot_label_data" in obj:
                description = obj["dot_label_data"].get("description", "No description")
                animdata = obj["dot_label_data"].get("animdata", "No animation data")
                box.label(text=f"Description: {description}")
                box.label(text=f"Animation Data: {animdata}")
            
            # Show current mesh name
            if obj.data:
                box.label(text=f"Mesh Name: {obj.data.name}")
            
            # Edit button
            box.operator("dot.edit_properties")

        # Animation tools section
        box = layout.box()
        box.label(text="Animation Tools")
        box.operator("dot.shift_animation")
        box.operator("dot.add_timeline_markers")
        box.operator("dot.sync_markers_to_data")

        # Export button
        layout.separator()
        layout.operator("dot.export_data")

        # --- NEW: Dictionary Management ---
        box = layout.box()
        box.label(text="Dictionary Management")
        box.operator("dot.add_word_to_dictionary", icon='PLUS')
        # --- END NEW ---

def draw_mesh_name(context):
    if not context:
        return

    # Get the current viewport
    view3d = context.space_data
    if not view3d:
        return

    # Get the current region
    region = context.region
    if not region:
        return

    # Get the current view matrix
    view_matrix = context.region_data.view_matrix

    # Set up the font
    font_id = 0
    blf.size(font_id, 12)
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)

    # Draw mesh names for all objects
    for obj in context.scene.objects:
        if obj.type == 'MESH':
            # Get the object's center in screen space
            center = obj.location
            center_screen = bpy_extras.view3d_utils.location_3d_to_region_2d(
                region, view3d.region_3d, center)

            if center_screen:
                # Draw the mesh data block name
                blf.position(font_id, center_screen[0], center_screen[1], 0)
                blf.draw(font_id, obj.data.name)

def get_keyframe_data(obj):
    """Get keyframe data from object's scale animation"""
    if not obj or not obj.animation_data or not obj.animation_data.action:
        return None
    
    action = obj.animation_data.action
    fcurves = [fc for fc in action.fcurves if fc.data_path == "scale"]
    if not fcurves:
        return None
    
    keyframes = set()
    for fc in fcurves:
        for key in fc.keyframe_points:
            keyframes.add(int(key.co.x))
    
    if keyframes:
        return f"{min(keyframes)}-{max(keyframes)}"
    return None

def get_marker_animation_data(context):
    """Get animation data from timeline markers"""
    scene = context.scene
    markers = []
    
    # Get the current frame
    current_frame = scene.frame_current
    
    # Collect all markers
    for marker in scene.timeline_markers:
        # Only consider markers that are close to the current frame (within 100 frames)
        if abs(marker.frame - current_frame) <= 100:
            markers.append((marker.frame, marker.name))
    
    # Sort markers by frame
    markers.sort(key=lambda x: x[0])
    
    # Find pairs of markers that could represent animation ranges
    ranges = []
    for i in range(len(markers) - 1):
        start_frame, start_name = markers[i]
        end_frame, end_name = markers[i + 1]
        
        # Check if markers are close enough to be a range (within 200 frames)
        if end_frame - start_frame <= 200:
            ranges.append({
                'start_frame': start_frame,
                'end_frame': end_frame,
                'start_name': start_name,
                'end_name': end_name,
                'range': f"{start_frame}-{end_frame}"
            })
    
    return ranges

def get_last_marker_range(context):
    """Return the range between the last two timeline markers as a string 'start-end', or None if not enough markers."""
    scene = context.scene
    markers = sorted(scene.timeline_markers, key=lambda m: m.frame)
    if len(markers) >= 2:
        start = markers[-2].frame
        end = markers[-1].frame
        return f"{start}-{end}", markers[-2].name, markers[-1].name
    return None, None, None

class DOT_OT_quick_create_label(bpy.types.Operator):
    bl_idname = "dot.quick_create_label"
    bl_label = "Quick Create Label"
    bl_description = "Quickly creates a new dot label at selected object position"
    
    description: bpy.props.StringProperty(
        name="Description",
        default="",
        description="Description for this label"
    )
    animdata: bpy.props.StringProperty(
        name="Animation Data",
        default="",
        description="Animation data in format: start_frame-end_frame"
    )
    
    _current_suggestions = []
    _last_marker_range = None
    _last_marker_names = (None, None)
    
    def invoke(self, context, event):
        # Suggest animation data from the last two timeline markers only
        marker_range, start_name, end_name = get_last_marker_range(context)
        self._last_marker_range = marker_range
        self._last_marker_names = (start_name, end_name)
        if marker_range:
            self.animdata = marker_range
        return context.window_manager.invoke_props_dialog(self)
    
    def execute(self, context):
        try:
            # Get position and rotation from selected object or 3D cursor
            if context.selected_objects:
                obj = context.selected_objects[0]
                loc = obj.location.copy()
                rot = obj.rotation_euler.copy()
            else:
                loc = context.scene.cursor.location.copy()
                rot = (0, 0, 0)
            
            # Get next label number
            num = get_next_label_number()
            label_name = f"label-{str(num).zfill(3)}"
            dot_name = f"dot-{str(num).zfill(3)}"
            
            # Create base meshes
            bpy.ops.mesh.primitive_cube_add(size=0.01)
            base_cube = bpy.context.object
            base_cube.data.name = "Cube.label.mesh"
            cube_mesh = base_cube.data.copy()
            bpy.data.objects.remove(base_cube)
            
            bpy.ops.mesh.primitive_ico_sphere_add(radius=0.01, subdivisions=1)
            base_sphere = bpy.context.object
            base_sphere.data.name = "Icosphere.dot.mesh"
            sphere_mesh = base_sphere.data.copy()
            bpy.data.objects.remove(base_sphere)
            
            # Create transparent material
            transparent_mat = create_transparent_material("Dot_Transparent_Mat")
            
            # Create label cube
            label_obj = bpy.data.objects.new(label_name, cube_mesh)
            label_obj.location = loc
            label_obj.rotation_euler = rot
            label_obj.scale = (0.01, 0.01, 0.01)
            context.collection.objects.link(label_obj)
            label_obj.data.materials.append(transparent_mat)
            label_obj.display_type = 'WIRE'
            label_obj.show_all_edges = True
            label_obj.show_wire = True
            label_obj.show_name = True
            
            # Store description and animation data
            if self.description or self.animdata:
                label_obj["dot_label_data"] = {
                    "description": self.description,
                    "animdata": self.animdata
                }
                
                # Add description to suggester
                if self.description:
                    description_suggester.add_description(self.description)
                    description_suggester.save_data()
            
            # Create dot sphere
            dot_obj = bpy.data.objects.new(dot_name, sphere_mesh)
            dot_obj.location = loc
            dot_obj.rotation_euler = rot
            dot_obj.scale = (0.01, 0.01, 0.01)
            context.collection.objects.link(dot_obj)
            dot_obj.data.materials.append(transparent_mat)
            dot_obj.show_name = True
            
            # Store description and animation data
            if self.description or self.animdata:
                dot_obj["dot_label_data"] = {
                    "description": self.description,
                    "animdata": self.animdata
                }
            
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error creating quick label: {str(e)}")
            return {'CANCELLED'}
    
    def draw(self, context):
        layout = self.layout
        # Description field with spell checking
        box = layout.box()
        box.label(text="Description:")
        row = box.row()
        row.prop(self, "description", text="")
        if self.description:
            self._current_suggestions = description_suggester.check_description(self.description)
            if self._current_suggestions:
                box.label(text="Suggestions:")
                for suggestion in self._current_suggestions:
                    row = box.row()
                    row.label(text=f"'{suggestion['word']}' → {', '.join(suggestion['suggestions'])}")
        # Animation data field with only last marker range suggestion
        box = layout.box()
        box.label(text="Animation Data:")
        row = box.row()
        row.prop(self, "animdata", text="")
        if self._last_marker_range:
            box.label(text="Last Marker Range:")
            row = box.row()
            start_name, end_name = self._last_marker_names
            label_text = f"{start_name} → {end_name}: {self._last_marker_range}" if start_name and end_name else self._last_marker_range
            row.label(text=label_text)
            op = row.operator("dot.use_last_marker_range", text="Use")
            op.range = self._last_marker_range

class DOT_OT_use_last_marker_range(bpy.types.Operator):
    bl_idname = "dot.use_last_marker_range"
    bl_label = "Use Last Marker Range"
    bl_description = "Use the last marker range for animation data"
    
    range: bpy.props.StringProperty(
        name="Range",
        default="",
        description="Animation range to use"
    )
    
    def execute(self, context):
        for op in context.window_manager.operators:
            if op.bl_idname == "dot.quick_create_label":
                op.animdata = self.range
                context.area.tag_redraw()
                break
        return {'FINISHED'}

class DOT_OT_add_word_to_dictionary(bpy.types.Operator):
    bl_idname = "dot.add_word_to_dictionary"
    bl_label = "Add Word to Dictionary"
    bl_description = "Manually add a word or phrase to the description suggester dictionary"
    
    new_word: bpy.props.StringProperty(
        name="Word/Phrase",
        default="",
        description="Enter word or phrase to add to the dictionary"
    )

    def execute(self, context):
        if self.new_word:
            description_suggester.add_description(self.new_word)
            description_suggester.save_data()
            self.report({'INFO'}, f"'{self.new_word}' added to dictionary.")
        else:
            self.report({'WARNING'}, "Please enter a word or phrase.")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "new_word")

def register():
    bpy.utils.register_class(AutoLM_UpdatePanel)
    bpy.utils.register_class(DOT_OT_create_label)
    bpy.utils.register_class(DOT_OT_export_data)
    bpy.utils.register_class(DOT_OT_edit_properties)
    bpy.utils.register_class(DOT_OT_shift_animation)
    bpy.utils.register_class(DOT_OT_add_timeline_markers)
    bpy.utils.register_class(DOT_OT_sync_markers_to_data)
    bpy.utils.register_class(DOT_OT_quick_create_label)
    bpy.utils.register_class(DOT_OT_use_last_marker_range)
    bpy.utils.register_class(DOT_OT_add_word_to_dictionary)
    bpy.utils.register_class(DOT_PT_label_panel)
    
    # Add drawing handler for mesh names
    _draw_handlers.append(bpy.types.SpaceView3D.draw_handler_add(
        draw_mesh_name, (None,), 'WINDOW', 'POST_PIXEL'))

    # Register the keyboard shortcut
    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')
    kmi = km.keymap_items.new('dot.quick_create_label', 'Q', 'PRESS', ctrl=True, shift=True)

def unregister():
    # Remove drawing handlers
    for handler in _draw_handlers:
        bpy.types.SpaceView3D.draw_handler_remove(handler, 'WINDOW')
    _draw_handlers.clear()
    
    bpy.utils.unregister_class(DOT_OT_create_label)
    bpy.utils.unregister_class(DOT_OT_export_data)
    bpy.utils.unregister_class(DOT_OT_edit_properties)
    bpy.utils.unregister_class(DOT_OT_shift_animation)
    bpy.utils.unregister_class(DOT_OT_add_timeline_markers)
    bpy.utils.unregister_class(DOT_OT_sync_markers_to_data)
    bpy.utils.unregister_class(DOT_OT_quick_create_label)
    bpy.utils.unregister_class(DOT_OT_use_last_marker_range)
    bpy.utils.unregister_class(DOT_OT_add_word_to_dictionary)
    bpy.utils.unregister_class(DOT_PT_label_panel)

    # Remove the keyboard shortcut
    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.get('Object Mode')
    if km:
        for kmi in km.keymap_items:
            if kmi.idname == 'dot.quick_create_label':
                km.keymap_items.remove(kmi)
                break

if __name__ == "__main__":
    register()