extends RefCounted
class_name OriginalRigLoader

const RIG_DB_PATH := "res://assets/combat_source/original_rigs.json"
const TEXTURE_ROOT := "res://assets/unity_original/textures/"

var _database: Dictionary = {}

func _load_database() -> bool:
	if not _database.is_empty():
		return true
	if not FileAccess.file_exists(RIG_DB_PATH):
		push_error("Original Unity rig database missing: " + RIG_DB_PATH)
		return false
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(RIG_DB_PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("Original Unity rig database is invalid JSON")
		return false
	_database = parsed
	return true

func create_rig(parent: Node3D, rig_name: String, apply_model_parent: bool = false) -> Dictionary:
	if not _load_database() or not _database.has(rig_name):
		push_error("Original rig not found: " + rig_name)
		return {}
	var rig: Dictionary = _database[rig_name]
	var root := Node3D.new()
	root.name = rig_name + "_OriginalModel"
	if apply_model_parent:
		root.transform = _transform_from_record(rig.get("model_parent_transform", {}))
	parent.add_child(root)

	var skeleton := Skeleton3D.new()
	skeleton.name = "OriginalAvatarSkeleton"
	var bone_records: Array = rig.get("bones", [])
	var bone_names: Array[String] = []
	var used_names: Dictionary = {}
	for i in range(bone_records.size()):
		var base_name := String(bone_records[i].get("name", "bone"))
		var final_name := base_name
		if used_names.has(final_name):
			final_name = "%s_%d" % [base_name, i]
		used_names[final_name] = true
		bone_names.append(final_name)
		skeleton.add_bone(final_name)
	for i in range(bone_records.size()):
		var record: Dictionary = bone_records[i]
		var parent_index := int(record.get("parent", -1))
		if parent_index >= 0 and parent_index < i:
			skeleton.set_bone_parent(i, parent_index)
		skeleton.set_bone_rest(i, _transform_from_record(record))
	root.add_child(skeleton)
	skeleton.transform = _transform_from_record(rig.get("skeleton_transform", {}))

	var skin := Skin.new()
	var bind_poses: Array = rig.get("bind_poses", [])
	var bone_map: Array = rig.get("mesh_bone_to_avatar", [])
	for i in range(mini(bind_poses.size(), bone_map.size())):
		skin.add_bind(int(bone_map[i]), _matrix_to_transform(bind_poses[i]))

	var array_mesh := ArrayMesh.new()
	var surfaces: Array = rig.get("surfaces", [])
	for surface_index in range(surfaces.size()):
		var surface: Dictionary = surfaces[surface_index]
		var arrays: Array = []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = _to_vec3_array(surface.get("vertices", []))
		arrays[Mesh.ARRAY_NORMAL] = _to_vec3_array(surface.get("normals", []))
		arrays[Mesh.ARRAY_TEX_UV] = _to_vec2_array(surface.get("uvs", []))
		arrays[Mesh.ARRAY_BONES] = _to_int_array(surface.get("bones", []))
		arrays[Mesh.ARRAY_WEIGHTS] = _to_float_array(surface.get("weights", []))
		arrays[Mesh.ARRAY_INDEX] = _to_int_array(surface.get("indices", []))
		array_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		var material_index := int(surface.get("material_index", surface_index))
		var texture_names: Array = rig.get("textures", [])
		if material_index >= 0 and material_index < texture_names.size():
			var texture_name := String(texture_names[material_index])
			if not texture_name.is_empty():
				var texture := _load_original_texture(texture_name)
				if texture:
					var material := StandardMaterial3D.new()
					material.albedo_texture = texture
					material.roughness = 1.0
					array_mesh.surface_set_material(surface_index, material)

	var mesh_instance := MeshInstance3D.new()
	mesh_instance.name = rig_name + "_OriginalSkinnedMesh"
	mesh_instance.mesh = array_mesh
	mesh_instance.skin = skin
	mesh_instance.transform = _transform_from_record(rig.get("mesh_transform", {}))
	root.add_child(mesh_instance)
	mesh_instance.skeleton = mesh_instance.get_path_to(skeleton)
	return {
		"root": root,
		"skeleton": skeleton,
		"mesh_instance": mesh_instance,
		"bone_names": bone_names,
		"rig_data": rig
	}

func create_bone_attachment(skeleton: Skeleton3D, bone_name: String, attachment_name: String = "WeaponSocket") -> BoneAttachment3D:
	var attachment := BoneAttachment3D.new()
	attachment.name = attachment_name
	attachment.bone_name = bone_name
	skeleton.add_child(attachment)
	return attachment

func _load_original_texture(file_name: String) -> Texture2D:
	var paths := [
		TEXTURE_ROOT + file_name,
		"res://assets/unity_original/bundle_assets/" + file_name
	]
	for path in paths:
		if ResourceLoader.exists(path):
			var resource = load(path)
			if resource is Texture2D:
				return resource
	return null

func _to_vec3_array(values: Array) -> PackedVector3Array:
	var result := PackedVector3Array()
	for value in values:
		result.append(Vector3(float(value[0]), float(value[1]), float(value[2])))
	return result

func _to_vec2_array(values: Array) -> PackedVector2Array:
	var result := PackedVector2Array()
	for value in values:
		result.append(Vector2(float(value[0]), float(value[1])))
	return result

func _to_int_array(values: Array) -> PackedInt32Array:
	var result := PackedInt32Array()
	for value in values:
		if value is Array:
			for item in value:
				result.append(int(item))
		else:
			result.append(int(value))
	return result

func _to_float_array(values: Array) -> PackedFloat32Array:
	var result := PackedFloat32Array()
	for value in values:
		if value is Array:
			for item in value:
				result.append(float(item))
		else:
			result.append(float(value))
	return result

func _transform_from_record(record: Dictionary) -> Transform3D:
	var position: Array = record.get("position", [0.0, 0.0, 0.0])
	var rotation: Array = record.get("rotation", [0.0, 0.0, 0.0, 1.0])
	var scale: Array = record.get("scale", [1.0, 1.0, 1.0])
	var q := Quaternion(float(rotation[0]), float(rotation[1]), float(rotation[2]), float(rotation[3]))
	var basis := Basis(q).scaled(Vector3(float(scale[0]), float(scale[1]), float(scale[2])))
	return Transform3D(basis, Vector3(float(position[0]), float(position[1]), float(position[2])))

func _matrix_to_transform(value: Variant) -> Transform3D:
	var rows: Array = value
	if value is Dictionary:
		rows = value.get("matrix4x4", [])
	if rows.size() == 16 and not (rows[0] is Array):
		rows = [rows.slice(0,4), rows.slice(4,8), rows.slice(8,12), rows.slice(12,16)]
	if rows.size() < 4:
		return Transform3D.IDENTITY
	var basis := Basis(
		Vector3(float(rows[0][0]), float(rows[1][0]), float(rows[2][0])),
		Vector3(float(rows[0][1]), float(rows[1][1]), float(rows[2][1])),
		Vector3(float(rows[0][2]), float(rows[1][2]), float(rows[2][2]))
	)
	var origin := Vector3(float(rows[0][3]), float(rows[1][3]), float(rows[2][3]))
	return Transform3D(basis, origin)
