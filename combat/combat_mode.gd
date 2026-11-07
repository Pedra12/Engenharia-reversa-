extends Node3D

const BOT_SCRIPT = preload("res://combat/combat_bot.gd")
const RIG_LOADER_SCRIPT = preload("res://combat/original_rig_loader.gd")
const WEAPON_ANIMATION_PLAYER_SCRIPT = preload("res://combat/original_weapon_animation_player.gd")
const COMBAT_RADAR_SCRIPT = preload("res://combat/combat_radar.gd")
const WEAPON_CATALOG: Array[Dictionary] = [
	{"name": "Fuzil", "damage": 24.0, "fire_rate": 10.0, "magazine": 30, "reserve": 120, "spread": 0.012, "pellets": 1, "recoil": 0.020, "reload": 1.8, "zoom": 1.5, "range": 70.0},
	{"name": "SMG", "damage": 15.0, "fire_rate": 15.38, "magazine": 40, "reserve": 160, "spread": 0.020, "pellets": 1, "recoil": 0.012, "reload": 1.5, "zoom": 1.3, "range": 70.0},
	{"name": "Escopeta", "damage": 12.0, "fire_rate": 1.11, "magazine": 8, "reserve": 32, "spread": 0.070, "pellets": 8, "recoil": 0.060, "reload": 2.2, "zoom": 1.2, "range": 45.0},
	{"name": "Sniper", "damage": 95.0, "fire_rate": 0.77, "magazine": 5, "reserve": 20, "spread": 0.001, "pellets": 1, "recoil": 0.090, "reload": 2.4, "zoom": 4.0, "range": 110.0},
	{"name": "Pistola", "damage": 34.0, "fire_rate": 3.33, "magazine": 12, "reserve": 48, "spread": 0.008, "pellets": 1, "recoil": 0.040, "reload": 1.2, "zoom": 1.3, "range": 55.0}
]
const UMP_MESH_PATH = "res://assets/combat_source/meshes/UMP_45_2.obj"
const SOLDIER_TEXTURE_PATH = "res://assets/combat_source/textures/SimpleMilitary_Soldier01_Black_-6561600483854028127.png"
const UMP_TEXTURE_PATH = "res://assets/combat_source/textures/UMP_45_Diffuse_-7805003812694618604.png"
const GRASS_STEP_PATH = "res://assets/combat_source/audio/footstep_grass_0_1_footstep_grass_0.wav"
const JUMP_SOUND_PATH = "res://assets/combat_source/audio/Jump_1_Jump.wav"
const RELOAD_VOICE_PATH = "res://assets/unity_original/bundle_assets/Android_blockgun1_assets_all_9b49dc55ce850c62b2c9e2e3b2f8f691.bundle/audio/AudioClip_VO_i_need_to_reload_0_5496395648634470501_VO_i_need_to_reload_0.wav.wav"

var map_root: Node3D
var return_callback: Callable
var player: CharacterBody3D
var camera: Camera3D
var camera_pivot: Node3D
var weapon_mount: Node3D
var weapon_mesh: MeshInstance3D
var rig_loader: OriginalRigLoader
var player_fp_rig: Dictionary
var player_weapon_attachment: BoneAttachment3D
var weapon_animation_player: OriginalWeaponAnimationPlayer
var weapon_sway: Node3D
var weapon_material: StandardMaterial3D
var hud: Control
var health_label: Label
var ammo_label: Label
var kills_label: Label
var status_label: Label
var hit_label: Label
var pause_button: Button
var radar: Control
var joystick_bg: Panel
var joystick_knob: Panel
var joystick_home_position := Vector2.ZERO
var move_vector := Vector2.ZERO
var move_touch_id := -1
var look_touch_id := -1
var look_yaw := 0.0
var look_pitch := -0.10
var health := 100
var ammo := 30
var reserve_ammo := 120
var weapon_index := 0
var weapon_magazines: Array[int] = []
var weapon_reserves: Array[int] = []
var kills := 0
var allied_kills := 0
var enemy_kills := 0
var match_finished := false
var pickup_areas: Array[Area3D] = []
var pickup_respawn_timers: Array[float] = []
var pickup_types: Array[int] = []
var fire_cooldown := 0.0
var reload_timer := 0.0
var footstep_timer := 0.0
var aiming := false
var crouching := false
var fire_left_held := false
var fire_right_held := false
var dead_timer := 0.0
var spawn_position := Vector3.ZERO
var original_spawn_data: Dictionary = {}
var used_spawn_positions: Array[Vector3] = []
var navigation_region: NavigationRegion3D
var original_offmesh_root: Node3D
var grass_player: AudioStreamPlayer3D
var jump_player: AudioStreamPlayer3D
var reload_player: AudioStreamPlayer
var rng := RandomNumberGenerator.new()

func begin(existing_map: Node3D, on_return: Callable) -> void:
	map_root = existing_map
	return_callback = on_return
	rng.randomize()
	_initialize_weapon_inventory()
	_prepare_assets()
	_load_original_spawn_points()
	_create_navigation_region()
	_create_player()
	_create_bots()
	_create_pickups()
	_build_hud()
	print("COMBAT_MODE_READY map=Floresta allies=2 enemies=4 weapon=UMP45")

func _prepare_assets() -> void:
	rig_loader = RIG_LOADER_SCRIPT.new()
	weapon_material = StandardMaterial3D.new()
	var weapon_texture = load(UMP_TEXTURE_PATH)
	if weapon_texture is Texture2D:
		weapon_material.albedo_texture = weapon_texture
	weapon_material.roughness = 0.72

func _find_floor(reference: Vector3, radius: float = 32.0) -> Dictionary:
	var space = get_world_3d().direct_space_state
	var offsets: Array[Vector2] = [Vector2.ZERO]
	for ring in [6.0, 12.0, 18.0, 24.0, 30.0]:
		for angle_index in range(12):
			var angle = TAU * float(angle_index) / 12.0
			offsets.append(Vector2(cos(angle), sin(angle)) * ring)
	var best: Dictionary = {}
	var best_distance := INF
	for offset in offsets:
		if offset.length() > radius:
			continue
		var xz = reference + Vector3(offset.x, 0.0, offset.y)
		var query = PhysicsRayQueryParameters3D.create(xz + Vector3.UP * 180.0, xz - Vector3.UP * 420.0)
		query.collision_mask = 1
		query.hit_back_faces = true
		var hit = space.intersect_ray(query)
		if hit.is_empty() or hit.normal.y < 0.62:
			continue
		var collider_name = String(hit.collider.name) if hit.collider else ""
		if collider_name.contains("forest_s3"):
			continue
		var distance = offset.length()
		if distance < best_distance:
			best_distance = distance
			best = hit
	return best

func _load_original_spawn_points() -> void:
	var path := "res://assets/combat_source/original_forest_spawn_points.json"
	if not FileAccess.file_exists(path):
		push_warning("Original forest spawn data unavailable; using map bounds.")
		return
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(parsed) == TYPE_DICTIONARY:
		original_spawn_data = parsed

func _create_navigation_region() -> void:
	var path := "res://assets/combat_source/original_forest_navmesh.json"
	if not FileAccess.file_exists(path):
		push_warning("Original forest NavMesh data unavailable; bots will use direct movement.")
		return
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_warning("Original forest NavMesh JSON could not be parsed.")
		return
	var nav_data: Dictionary = parsed
	var settings: Dictionary = nav_data.get("settings", {})
	var nav_mesh := NavigationMesh.new()
	nav_mesh.agent_height = float(settings.get("agent_height", 2.0))
	nav_mesh.agent_radius = float(settings.get("agent_radius", 0.4))
	nav_mesh.agent_max_slope = float(settings.get("agent_slope", 60.0))
	nav_mesh.agent_max_climb = float(settings.get("agent_climb", 0.5))
	nav_mesh.cell_size = float(settings.get("cell_size", 0.09))
	# Match the Godot navigation map rasterizer to Unity's original 0.09 m cell.
	# The default Godot map cell size (0.25 m) merges the recovered Unity triangles incorrectly.
	var nav_map: RID = get_world_3d().navigation_map
	NavigationServer3D.map_set_cell_size(nav_map, nav_mesh.cell_size)
	NavigationServer3D.map_set_merge_rasterizer_cell_scale(nav_map, 0.001)
	var nav_vertices := PackedVector3Array()
	for value in nav_data.get("vertices", []):
		nav_vertices.append(Vector3(float(value[0]), float(value[1]), float(value[2])))
	nav_mesh.vertices = nav_vertices
	var polygon_count := 0
	for triangle in nav_data.get("triangles", []):
		if triangle.size() == 3:
			nav_mesh.add_polygon(PackedInt32Array([int(triangle[0]), int(triangle[1]), int(triangle[2])]))
			polygon_count += 1
	if polygon_count < 1000:
		push_warning("Original forest NavMesh contains too few polygons: %d" % polygon_count)
		return
	navigation_region = NavigationRegion3D.new()
	navigation_region.name = "OriginalForestNavigationRegion"
	navigation_region.navigation_layers = 1
	navigation_region.navigation_mesh = nav_mesh
	map_root.add_child(navigation_region)

	original_offmesh_root = Node3D.new()
	original_offmesh_root.name = "OriginalForestOffMeshLinks"
	map_root.add_child(original_offmesh_root)
	var link_count := 0
	var seen_links: Dictionary = {}
	for link_data in nav_data.get("off_mesh_links", []):
		var start_values: Array = link_data.get("start", [])
		var end_values: Array = link_data.get("end", [])
		if start_values.size() < 3 or end_values.size() < 3:
			continue
		var start_position := Vector3(float(start_values[0]), float(start_values[1]), float(start_values[2]))
		var end_position := Vector3(float(end_values[0]), float(end_values[1]), float(end_values[2]))
		var key := "%0.2f,%0.2f,%0.2f>%0.2f,%0.2f,%0.2f" % [start_position.x, start_position.y, start_position.z, end_position.x, end_position.y, end_position.z]
		if seen_links.has(key):
			continue
		seen_links[key] = true
		var link := NavigationLink3D.new()
		link.name = "OriginalOffMeshLink_%04d" % link_count
		link.start_position = start_position
		link.end_position = end_position
		link.bidirectional = int(link_data.get("direction", 0)) == 0
		link.navigation_layers = 1
		link.enter_cost = 1.0
		link.travel_cost = 1.0
		original_offmesh_root.add_child(link)
		link_count += 1
	print("ORIGINAL_FOREST_NAVMESH_READY vertices=", nav_vertices.size(), " polygons=", polygon_count, " offmesh_links=", link_count)

func _get_original_spawn_positions(group: String) -> Array[Vector3]:
	var result: Array[Vector3] = []
	var groups: Dictionary = original_spawn_data.get("spawn_groups", {})
	for entry in groups.get(group, []):
		var value: Array = entry.get("godot_position", [])
		if value.size() >= 3:
			result.append(Vector3(float(value[0]), float(value[1]), float(value[2])))
	return result

func _choose_spawn_position(candidates: Array[Vector3], used: Array[Vector3]) -> Vector3:
	if candidates.is_empty():
		return _map_center()
	var best := candidates[rng.randi_range(0, candidates.size() - 1)]
	var best_distance := -1.0
	for candidate in candidates:
		var minimum_distance := INF
		if used.is_empty():
			minimum_distance = rng.randf()
		else:
			var candidate_2d := Vector2(candidate.x, candidate.z)
			for occupied in used:
				minimum_distance = minf(minimum_distance, candidate_2d.distance_to(Vector2(occupied.x, occupied.z)))
		if minimum_distance > best_distance:
			best_distance = minimum_distance
			best = candidate
	return best

func _map_center() -> Vector3:
	var bounds := AABB()
	var found := false
	for item in map_root.find_children("*", "MeshInstance3D", true, false):
		if item is MeshInstance3D and item.mesh:
			var box: AABB = item.global_transform * item.mesh.get_aabb()
			if not found:
				bounds = box
				found = true
			else:
				bounds = bounds.merge(box)
	var center_data: Dictionary = original_spawn_data.get("map_center", {})
	var center_values: Array = center_data.get("godot", [])
	if center_values.size() >= 3:
		var original_center := Vector3(float(center_values[0]), float(center_values[1]), float(center_values[2]))
		if not found or bounds.grow(15.0).has_point(original_center):
			return original_center
	if found:
		return bounds.get_center()
	return map_root.global_position

func _create_player() -> void:
	player = CharacterBody3D.new()
	player.name = "CombatPlayer"
	player.collision_layer = 2
	player.collision_mask = 5 # world (1) + bots (3)
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.4
	capsule.height = 1.8
	var collision := CollisionShape3D.new()
	collision.shape = capsule
	collision.position.y = 0.9
	player.add_child(collision)
	player.floor_snap_length = 0.3
	map_root.add_child(player)
	var center := _map_center()
	var original_points := _get_original_spawn_positions("generic")
	var requested_spawn := _choose_spawn_position(original_points, [])
	var floor_hit := _find_floor(requested_spawn if not original_points.is_empty() else center)
	if floor_hit.is_empty():
		floor_hit = _find_floor(center)
	if floor_hit.is_empty():
		spawn_position = center + Vector3.UP * 4.0
		push_warning("Combat spawn fallback used; no safe floor ray was found.")
	else:
		spawn_position = floor_hit.position + Vector3.UP * 0.12
	used_spawn_positions.clear()
	used_spawn_positions.append(spawn_position)
	player.global_position = spawn_position
	camera_pivot = Node3D.new()
	camera_pivot.position = Vector3(0.0, 1.58, 0.0)
	player.add_child(camera_pivot)
	camera = Camera3D.new()
	camera.position = Vector3.ZERO
	camera.fov = 70.0
	camera.near = 0.05
	camera.current = true
	camera_pivot.add_child(camera)
	weapon_mount = Node3D.new()
	weapon_mount.name = "WeaponRecoilPivot"
	camera.add_child(weapon_mount)
	weapon_sway = Node3D.new()
	weapon_sway.name = "WeaponSwayPivot"
	weapon_mount.add_child(weapon_sway)
	player_fp_rig = rig_loader.create_ump45_fp(weapon_sway)
	if player_fp_rig.is_empty():
		push_error("Original skinned UMP45 + Hands first-person prefab could not be created.")
	else:
		weapon_mesh = player_fp_rig.get("meshes", {}).get("weapon")
		weapon_animation_player = WEAPON_ANIMATION_PLAYER_SCRIPT.new()
		weapon_mount.add_child(weapon_animation_player)
		weapon_animation_player.setup(player_fp_rig.get("rig_data", {}), player_fp_rig["skeleton"])
		weapon_animation_player.sound_event.connect(_on_weapon_sound_event)
		weapon_animation_player.clip_finished.connect(_on_weapon_clip_finished)
		weapon_animation_player.play("Deploy", 1.0, false)
		var fp_weapon: MeshInstance3D = player_fp_rig.get("meshes", {}).get("weapon")
		if fp_weapon and fp_weapon.mesh:
			print("FP_WEAPON_AABB name=", fp_weapon.name, " aabb=", fp_weapon.mesh.get_aabb(), " global_transform=", fp_weapon.global_transform)
	_create_audio()
	call_deferred("_diagnose_player_floor")

func _diagnose_player_floor() -> void:
	await get_tree().physics_frame
	if not is_instance_valid(player):
		return
	var ray_start := player.global_position + Vector3.UP * 0.35
	var ray_end := player.global_position - Vector3.UP * 1.25
	var query := PhysicsRayQueryParameters3D.create(ray_start, ray_end)
	query.collision_mask = 1
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	var floor_name := String(hit.collider.name) if not hit.is_empty() and hit.collider else "NONE"
	print("PLAYER_FLOOR_DIAGNOSTIC position=", player.global_position, " is_on_floor=", player.is_on_floor(), " layer=", player.collision_layer, " mask=", player.collision_mask, " ray_body=", floor_name, " ray_point=", hit.get("position", Vector3.ZERO))

func _create_audio() -> void:
	grass_player = AudioStreamPlayer3D.new()
	grass_player.stream = load(GRASS_STEP_PATH)
	grass_player.volume_db = -12.0
	player.add_child(grass_player)
	jump_player = AudioStreamPlayer3D.new()
	jump_player.stream = load(JUMP_SOUND_PATH)
	jump_player.volume_db = -8.0
	player.add_child(jump_player)
	reload_player = AudioStreamPlayer.new()
	if ResourceLoader.exists(RELOAD_VOICE_PATH):
		reload_player.stream = load(RELOAD_VOICE_PATH)
	else:
		push_warning("Reload voice asset unavailable; continuing without reload voice: " + RELOAD_VOICE_PATH)
	reload_player.volume_db = -9.0
	add_child(reload_player)

func _create_bots() -> void:
	if not rig_loader:
		push_error("Original Unity rig loader missing; refusing to create placeholder enemies.")
		return
	var candidates := _get_original_spawn_positions("generic")
	var fallback_offsets := [Vector3(10, 0, 4), Vector3(-12, 0, -5), Vector3(5, 0, -15)]
	for index in range(6):
		var guess: Vector3 = _choose_spawn_position(candidates, used_spawn_positions) if not candidates.is_empty() else spawn_position + fallback_offsets[index]
		var floor_hit := _find_floor(guess, 8.0)
		if floor_hit.is_empty():
			floor_hit = _find_floor(spawn_position + fallback_offsets[index], 10.0)
		if floor_hit.is_empty():
			continue
		var bot := CharacterBody3D.new()
		bot.set_script(BOT_SCRIPT)
		bot.name = "BotSoldier_%02d" % (index + 1)
		map_root.add_child(bot)
		bot.global_position = floor_hit.position + Vector3.UP * 0.12
		used_spawn_positions.append(bot.global_position)
		var assigned_team := 0 if index < 2 else 1
		bot.call("configure", player, self, rig_loader, load(UMP_MESH_PATH), weapon_material, assigned_team)
	print("COMBAT_BOTS_SPAWNED count=", map_root.find_children("BotSoldier_*", "CharacterBody3D", true, false).size(), " original_generic_spawns=", candidates.size())

func _create_pickups() -> void:
	pickup_areas.clear()
	pickup_respawn_timers.clear()
	pickup_types.clear()
	for index in range(8):
		var pickup := Area3D.new()
		pickup.name = "ForestPickup_%02d" % (index + 1)
		pickup.collision_layer = 8
		pickup.collision_mask = 2
		pickup.monitoring = true
		var collision := CollisionShape3D.new()
		var sphere := SphereShape3D.new()
		sphere.radius = 1.25
		collision.shape = sphere
		pickup.add_child(collision)
		var mesh := MeshInstance3D.new()
		var crate := BoxMesh.new()
		crate.size = Vector3(0.62, 0.62, 0.62)
		mesh.mesh = crate
		var material := StandardMaterial3D.new()
		var is_health := index % 2 == 0
		material.albedo_color = Color(0.16, 0.9, 0.32) if is_health else Color(1.0, 0.72, 0.12)
		material.emission_enabled = true
		material.emission = material.albedo_color * 0.35
		mesh.material_override = material
		mesh.position.y = 0.48
		pickup.add_child(mesh)
		map_root.add_child(pickup)
		pickup.body_entered.connect(_on_pickup_body_entered.bind(index))
		pickup_areas.append(pickup)
		pickup_respawn_timers.append(0.0)
		pickup_types.append(0 if is_health else 1)
		_place_pickup(index)
	print("COMBAT_PICKUPS_READY count=", pickup_areas.size())

func _place_pickup(index: int) -> void:
	if index < 0 or index >= pickup_areas.size():
		return
	var candidates := _get_original_spawn_positions("generic")
	var reference := _choose_spawn_position(candidates, used_spawn_positions) if not candidates.is_empty() else _map_center() + Vector3(rng.randf_range(-25.0, 25.0), 0.0, rng.randf_range(-25.0, 25.0))
	var floor_hit := _find_floor(reference, 22.0)
	if floor_hit.is_empty():
		floor_hit = _find_floor(_map_center(), 30.0)
	if floor_hit.is_empty():
		pickup_areas[index].visible = false
		pickup_areas[index].monitoring = false
		push_warning("Pickup %d could not find a valid floor position." % index)
		return
	pickup_areas[index].global_position = floor_hit.position + Vector3.UP * 0.12
	pickup_areas[index].rotation.y = rng.randf_range(0.0, TAU)
	pickup_areas[index].visible = true
	pickup_areas[index].monitoring = true

func _on_pickup_body_entered(body: Node3D, index: int) -> void:
	if body != player or index < 0 or index >= pickup_areas.size():
		return
	if pickup_respawn_timers[index] > 0.0:
		return
	if pickup_types[index] == 0:
		var recovered := mini(40, 100 - health)
		health = mini(100, health + 40)
		status_label.text = "KIT MÉDICO +%d VIDA" % recovered if recovered > 0 else "VIDA JÁ ESTÁ COMPLETA"
	else:
		var total_added := 0
		for weapon_index_value in range(WEAPON_CATALOG.size()):
			var amount := maxi(1, int(float(WEAPON_CATALOG[weapon_index_value]["reserve"]) * 0.5))
			weapon_reserves[weapon_index_value] += amount
			total_added += amount
		reserve_ammo = weapon_reserves[weapon_index]
		status_label.text = "CAIXA DE MUNIÇÃO +%d" % total_added
	pickup_areas[index].visible = false
	pickup_areas[index].monitoring = false
	pickup_respawn_timers[index] = 20.0
	_update_hud()

func _update_pickup_respawns(delta: float) -> void:
	for index in range(pickup_respawn_timers.size()):
		if pickup_respawn_timers[index] <= 0.0:
			continue
		pickup_respawn_timers[index] = maxf(0.0, pickup_respawn_timers[index] - delta)
		if pickup_respawn_timers[index] <= 0.0:
			_place_pickup(index)

func _build_hud() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 30
	layer.process_mode = Node.PROCESS_MODE_ALWAYS
	add_child(layer)
	hud = Control.new()
	hud.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	hud.mouse_filter = Control.MOUSE_FILTER_PASS
	layer.add_child(hud)
	var top := Panel.new()
	top.position = Vector2(18, 16)
	top.size = Vector2(300, 88)
	_style_panel(top, Color(0.025, 0.045, 0.065, 0.82), 12)
	hud.add_child(top)
	health_label = _new_label(top, "VIDA 100 / 100", Vector2(14, 8), 22)
	ammo_label = _new_label(top, "UMP45  30 / 90", Vector2(14, 36), 18)
	kills_label = _new_label(top, "ELIMINAÇÕES 0", Vector2(172, 43), 15)
	status_label = _new_label(hud, "BATALHA EM FLORESTA", Vector2(0, 18), 18)
	status_label.set_anchors_preset(Control.PRESET_TOP_WIDE)
	status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hit_label = _new_label(hud, "+28", Vector2.ZERO, 30)
	hit_label.visible = false
	hit_label.set_anchors_preset(Control.PRESET_CENTER)
	pause_button = Button.new()
	pause_button.text = "Ⅱ"
	pause_button.position = Vector2(50.0, 50.0)
	pause_button.size = Vector2(65.0, 65.0)
	pause_button.add_theme_font_size_override("font_size", 26)
	pause_button.add_theme_color_override("font_color", Color(0.95, 0.98, 1.0))
	pause_button.pressed.connect(_toggle_pause)
	hud.add_child(pause_button)
	# Recovered from WindowPlayer/Content/MobileCanvas/ContentsOther/Advanced_FPS_Radar01.
	radar = COMBAT_RADAR_SCRIPT.new()
	radar.name = "OriginalStyleCombatRadar"
	radar.set_anchors_preset(Control.PRESET_TOP_LEFT)
	var radar_scale := minf(get_viewport().get_visible_rect().size.x / 1920.0, get_viewport().get_visible_rect().size.y / 1080.0)
	radar.position = Vector2(237.0, 196.0) * radar_scale
	radar.size = Vector2(310.32, 310.32) * radar_scale
	hud.add_child(radar)
	var screen := get_viewport().get_visible_rect().size
	var ui_scale := minf(screen.x / 1920.0, screen.y / 1080.0)
	# Positions and sizes recovered from WindowPlayer/Content/MobileCanvas in Unity.
	joystick_bg = Panel.new()
	# The original Joystick-DynamicRegion covers the full left half. The visual base
	# starts at the recovered default location and moves to the initial touch point.
	joystick_bg.set_anchors_preset(Control.PRESET_TOP_LEFT)
	joystick_bg.position = Vector2(167.0 * ui_scale, screen.y - 300.0 * ui_scale)
	joystick_bg.size = Vector2(250.0, 250.0) * ui_scale
	joystick_home_position = joystick_bg.position
	joystick_bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_style_panel(joystick_bg, Color(0.08, 0.12, 0.16, 0.28), 125)
	hud.add_child(joystick_bg)
	var joystick_base_path := _find_original_ui_texture("Sprite_ui_gameplay_left_joystick")
	if not joystick_base_path.is_empty():
		var joystick_base := TextureRect.new()
		joystick_base.texture = load(joystick_base_path)
		joystick_base.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		joystick_base.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		joystick_base.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		joystick_base.mouse_filter = Control.MOUSE_FILTER_IGNORE
		joystick_bg.add_child(joystick_base)
	joystick_knob = Panel.new()
	joystick_knob.size = Vector2(86.0, 86.0) * ui_scale
	joystick_knob.position = (joystick_bg.size - joystick_knob.size) * 0.5
	joystick_knob.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_style_panel(joystick_knob, Color(0.62, 0.78, 0.88, 0.68), 48)
	joystick_bg.add_child(joystick_knob)
	var joystick_knob_path := _find_original_ui_texture("Sprite_ui_gameplay_joystick_knob")
	if not joystick_knob_path.is_empty():
		var knob_texture := TextureRect.new()
		knob_texture.texture = load(joystick_knob_path)
		knob_texture.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		knob_texture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		knob_texture.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		knob_texture.mouse_filter = Control.MOUSE_FILTER_IGNORE
		joystick_knob.add_child(knob_texture)
	var fire_icon := _find_original_ui_texture("Sprite_CF-Button-Fire")
	var aim_icon := _find_original_ui_texture("Sprite_ui_icon_aim")
	var reload_icon := _find_original_ui_texture("Sprite_ui_icon_reload")
	_make_button("MIRA", Vector2(-420.5, -562.5) * ui_scale, Vector2(125.0, 125.0) * ui_scale, _toggle_aim, true, aim_icon)
	_make_button("PULAR", Vector2(-191.5, -423.5) * ui_scale, Vector2(125.0, 125.0) * ui_scale, _jump, true)
	_make_button("RECARREGAR", Vector2(-562.5, -419.5) * ui_scale, Vector2(125.0, 125.0) * ui_scale, _reload, true, reload_icon)
	_make_button("TROCAR", Vector2(-270.0, -270.0) * ui_scale, Vector2(112.0, 112.0) * ui_scale, _swap_weapon, true)
	_make_button("AGACHAR", Vector2(-422.5, -193.5) * ui_scale, Vector2(125.0, 125.0) * ui_scale, _toggle_crouch, true)
	_make_button("SAIR", Vector2(18.0, 116.0) * ui_scale, Vector2(88.0, 54.0) * ui_scale, _exit_combat, false)
	# Four independent thin bars keep the aim point truly centered at any aspect ratio.
	var crosshair := Control.new()
	crosshair.name = "CenterCrosshair"
	crosshair.set_anchors_preset(Control.PRESET_CENTER)
	crosshair.position = Vector2(-9.0, -9.0)
	crosshair.size = Vector2(18.0, 18.0)
	crosshair.mouse_filter = Control.MOUSE_FILTER_IGNORE
	hud.add_child(crosshair)
	for bar_data in [Vector4(8, 0, 2, 6), Vector4(8, 12, 2, 6), Vector4(0, 8, 6, 2), Vector4(12, 8, 6, 2)]:
		var bar := ColorRect.new()
		bar.position = Vector2(bar_data.x, bar_data.y)
		bar.size = Vector2(bar_data.z, bar_data.w)
		bar.color = Color(0.9, 1.0, 0.94, 0.9)
		bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
		crosshair.add_child(bar)

func _style_panel(panel: Panel, color: Color, radius: int) -> void:
	var style := StyleBoxFlat.new()
	style.bg_color = color
	style.set_corner_radius_all(radius)
	style.border_color = Color(0.55, 0.78, 0.9, 0.65)
	style.set_border_width_all(1)
	panel.add_theme_stylebox_override("panel", style)

func _new_label(parent: Control, value: String, pos: Vector2, size: int) -> Label:
	var label := Label.new()
	label.text = value
	label.position = pos
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", Color(0.91, 0.96, 1.0, 1.0))
	parent.add_child(label)
	return label

func _find_original_ui_texture(fragment: String) -> String:
	for root_path in ["res://assets/unity_original/textures", "res://assets/unity_original/bundle_assets"]:
		var found := _search_original_texture(root_path, fragment.to_lower())
		if not found.is_empty():
			return found
	return ""

func _search_original_texture(folder_path: String, fragment: String) -> String:
	var directory := DirAccess.open(folder_path)
	if directory == null:
		return ""
	for file_name in directory.get_files():
		if file_name.to_lower().contains(fragment) and file_name.to_lower().ends_with(".png"):
			return folder_path.path_join(file_name)
	for child_name in directory.get_directories():
		var found := _search_original_texture(folder_path.path_join(child_name), fragment)
		if not found.is_empty():
			return found
	return ""

func _make_button(value: String, offset: Vector2, dimensions: Vector2, callback: Callable, right: bool = true, icon_path: String = "") -> void:
	var button := Button.new()
	button.text = value
	button.size = dimensions
	if right:
		button.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
		button.position = offset
	else:
		button.set_anchors_preset(Control.PRESET_TOP_LEFT)
		button.position = offset
	if not icon_path.is_empty():
		var texture = load(icon_path)
		if texture is Texture2D:
			button.icon = texture
			button.expand_icon = true
	button.add_theme_font_size_override("font_size", 16)
	button.add_theme_color_override("font_color", Color(0.95, 0.98, 1.0))
	button.pressed.connect(callback)
	hud.add_child(button)

func _make_hold_button(value: String, offset: Vector2, dimensions: Vector2, right: bool, side: String, icon_path: String = "", center_left: bool = false) -> void:
	var button := Button.new()
	button.text = value
	button.size = dimensions
	if center_left:
		button.set_anchors_preset(Control.PRESET_CENTER_LEFT)
		button.position = offset
	elif right:
		button.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
		button.position = offset
	else:
		button.set_anchors_preset(Control.PRESET_TOP_LEFT)
		button.position = offset
	if not icon_path.is_empty():
		var texture = load(icon_path)
		if texture is Texture2D:
			button.icon = texture
			button.expand_icon = true
	button.add_theme_font_size_override("font_size", 17)
	button.add_theme_color_override("font_color", Color(1.0, 0.96, 0.88, 1.0))
	button.button_down.connect(_set_fire_button.bind(side, true))
	button.button_up.connect(_set_fire_button.bind(side, false))
	hud.add_child(button)

func _set_fire_button(side: String, pressed: bool) -> void:
	if side == "left":
		fire_left_held = pressed
	else:
		fire_right_held = pressed

# Capture touch input before GUI Buttons consume it. The previous _unhandled_input
# lost joystick/look touches whenever a Control accepted the event.
func _input(event: InputEvent) -> void:
	if event is InputEventScreenTouch:
		var screen := get_viewport().get_visible_rect().size
		if event.pressed:
			if event.position.x < screen.x * 0.5 and move_touch_id == -1:
				move_touch_id = event.index
				joystick_bg.position = event.position - joystick_bg.size * 0.5
				joystick_knob.position = (joystick_bg.size - joystick_knob.size) * 0.5
				_update_joystick(event.position)
			elif event.position.x >= screen.x * 0.5 and look_touch_id == -1 and not _touch_over_hud_button(event.position):
				look_touch_id = event.index
		else:
			if event.index == move_touch_id:
				move_touch_id = -1
				move_vector = Vector2.ZERO
				joystick_bg.position = joystick_home_position
				joystick_knob.position = (joystick_bg.size - joystick_knob.size) * 0.5
			if event.index == look_touch_id:
				look_touch_id = -1
	elif event is InputEventScreenDrag:
		if event.index == move_touch_id:
			_update_joystick(event.position)
		elif event.index == look_touch_id:
			_apply_look(event.relative)
	elif event is InputEventMouseMotion and Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT):
		_apply_look(event.relative)

func _touch_over_hud_button(point: Vector2) -> bool:
	if not is_instance_valid(hud):
		return false
	for control in hud.get_children():
		if control is Control and control is Button and control.visible and control.get_global_rect().has_point(point):
			return true
	return false

func _update_joystick(position: Vector2) -> void:
	var center := joystick_bg.get_global_rect().get_center()
	var offset := position - center
	var travel_radius := joystick_bg.size.x * 0.30
	if offset.length() > travel_radius:
		offset = offset.normalized() * travel_radius
	move_vector = Vector2(offset.x / travel_radius, -offset.y / travel_radius)
	joystick_knob.position = (joystick_bg.size - joystick_knob.size) * 0.5 + offset

func _apply_look(relative: Vector2) -> void:
	look_yaw -= relative.x * 0.004
	look_pitch = clampf(look_pitch - relative.y * 0.003, -0.72, 0.45)
	player.rotation.y = look_yaw
	camera_pivot.rotation.x = look_pitch

func _physics_process(delta: float) -> void:
	if not is_instance_valid(player):
		return
	_update_pickup_respawns(delta)
	if is_instance_valid(radar):
		radar.call("update_radar", player, map_root.find_children("BotSoldier_*", "CharacterBody3D", true, false))
	fire_cooldown = maxf(0.0, fire_cooldown - delta)
	if not match_finished and fire_cooldown <= 0.0 and reload_timer <= 0.0 and dead_timer <= 0.0 and _auto_fire_target_visible():
		_fire()
	if reload_timer > 0.0:
		reload_timer -= delta
		if reload_timer <= 0.0 and not (weapon_animation_player and weapon_animation_player.is_playing_clip("Reload")):
			_finish_reload()
	if dead_timer > 0.0:
		dead_timer -= delta
		if dead_timer <= 0.0:
			health = 100
			player.global_position = spawn_position
			player.velocity = Vector3.ZERO
			player.visible = true
			_update_hud()
			status_label.text = "VOCÊ RETORNOU AO COMBATE"
		else:
			# A dead player must not keep moving or firing invisibly before respawn.
			player.velocity = Vector3.ZERO
			return
	var input_dir = move_vector
	if Input.is_key_pressed(KEY_W): input_dir.y = 1.0
	if Input.is_key_pressed(KEY_S): input_dir.y = -1.0
	if Input.is_key_pressed(KEY_A): input_dir.x = -1.0
	if Input.is_key_pressed(KEY_D): input_dir.x = 1.0
	var gravity = float(ProjectSettings.get_setting("physics/3d/default_gravity", 9.8))
	if not player.is_on_floor():
		player.velocity.y -= gravity * delta
	var forward = Vector3(-sin(look_yaw), 0.0, -cos(look_yaw))
	var right = Vector3(cos(look_yaw), 0.0, -sin(look_yaw))
	var direction = (right * input_dir.x + forward * input_dir.y).normalized()
	var speed = (1.7 if crouching else 3.0) if aiming else (2.6 if crouching else 5.0)
	player.velocity.x = direction.x * speed
	player.velocity.z = direction.z * speed
	player.move_and_slide()
	if weapon_sway:
		var sway_target := Vector3(-input_dir.x * 0.018, absf(input_dir.y) * 0.012, 0.0)
		if aiming:
			sway_target *= 0.35
		weapon_sway.position = weapon_sway.position.lerp(sway_target, clampf(delta * 7.0, 0.0, 1.0))
	if direction.length() > 0.15:
		footstep_timer -= delta
		if footstep_timer <= 0.0 and grass_player and not grass_player.playing:
			grass_player.play()
			footstep_timer = 0.48
	if Input.is_key_pressed(KEY_SPACE):
		_jump()

func _auto_fire_target_visible() -> bool:
	if not is_instance_valid(camera) or not is_instance_valid(player):
		return false
	var origin := camera.global_position
	var direction := -camera.global_transform.basis.z
	var query := PhysicsRayQueryParameters3D.create(origin, origin + direction * 70.0)
	query.collision_mask = 5
	query.exclude = [player.get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	return not hit.is_empty() and hit.collider is Node and hit.collider.has_method("take_damage")

func _fire() -> void:
	if fire_cooldown > 0.0 or reload_timer > 0.0 or dead_timer > 0.0:
		return
	var weapon: Dictionary = WEAPON_CATALOG[weapon_index]
	if ammo <= 0:
		status_label.text = "SEM MUNIÇÃO: RECARREGANDO"
		_reload()
		return
	ammo -= 1
	fire_cooldown = 1.0 / float(weapon["fire_rate"])
	if weapon_animation_player:
		weapon_animation_player.play("Fire", 1.0, false)
	if weapon_mount:
		weapon_mount.position.z = float(weapon["recoil"])
		var tween := create_tween()
		tween.tween_property(weapon_mount, "position:z", 0.0, 0.09)
		camera_pivot.rotation.x = clampf(camera_pivot.rotation.x - float(weapon["recoil"]) * 0.8, -0.72, 0.45)
	_play_weapon_sound("ump45_fire")
	var origin := camera.global_position
	var forward := -camera.global_transform.basis.z
	var right := camera.global_transform.basis.x
	var up := camera.global_transform.basis.y
	for pellet in range(int(weapon["pellets"])):
		var spread := float(weapon["spread"])
		var direction := (forward + right * rng.randf_range(-spread, spread) + up * rng.randf_range(-spread, spread)).normalized()
		var query := PhysicsRayQueryParameters3D.create(origin, origin + direction * float(weapon["range"]))
		query.collision_mask = 5
		query.exclude = [player.get_rid()]
		var hit := get_world_3d().direct_space_state.intersect_ray(query)
		if hit.is_empty():
			continue
		var target = hit.collider
		if not target or not target.has_method("take_damage"):
			continue
		var relative_height: float = hit.position.y - target.global_position.y
		var headshot := relative_height > 1.42
		var legshot := relative_height < 0.52
		var damage := int(round(float(weapon["damage"]) * (1.18 if headshot else (0.8 if legshot else 1.0))))
		var killed: bool = target.take_damage(damage, headshot, 0, true)
		_show_damage(damage * (2 if headshot else 1), headshot)
		if headshot:
			status_label.text = "TIRO NA CABEÇA"
		elif killed:
			status_label.text = "ALVO ELIMINADO"
	_update_hud()

func _on_weapon_clip_finished(animation_name: String) -> void:
	if animation_name == "Reload":
		_finish_reload()

func _finish_reload() -> void:
	var capacity := int(WEAPON_CATALOG[weapon_index]["magazine"])
	if reload_timer <= 0.0 and ammo >= capacity:
		return
	var needed := capacity - ammo
	var loaded := mini(needed, reserve_ammo)
	ammo += loaded
	reserve_ammo -= loaded
	reload_timer = 0.0
	_update_hud()
	if is_instance_valid(status_label):
		status_label.text = "CARREGADOR COMPLETO" if loaded > 0 else "SEM MUNIÇÃO RESERVA"

func _on_weapon_sound_event(sound_name: String, resource_path: String) -> void:
	if resource_path.is_empty() or not ResourceLoader.exists(resource_path):
		return
	var sound := AudioStreamPlayer3D.new()
	sound.stream = load(resource_path)
	sound.volume_db = -5.0
	if is_instance_valid(player):
		player.add_child(sound)
	else:
		add_child(sound)
	sound.play()
	sound.finished.connect(sound.queue_free)

func _play_weapon_sound(sound_name: String) -> void:
	if not weapon_animation_player:
		return
	_on_weapon_sound_event(sound_name, weapon_animation_player.get_sound_path(sound_name))

func _show_damage(amount: int, headshot: bool) -> void:
	hit_label.text = ("HEADSHOT  " if headshot else "") + str(amount)
	hit_label.visible = true
	hit_label.modulate = Color(1.0, 0.78, 0.24, 1.0) if headshot else Color(1.0, 1.0, 1.0, 1.0)
	hit_label.position = Vector2(-80, -62)
	var tween = create_tween()
	tween.tween_property(hit_label, "position", Vector2(-80, -108), 0.42)
	tween.tween_callback(func(): hit_label.visible = false)

func get_best_target(source: CharacterBody3D, source_team: int) -> CharacterBody3D:
	var best: CharacterBody3D
	var best_distance := INF
	if source_team != 0 and dead_timer <= 0.0 and is_instance_valid(player) and player.visible:
		var player_distance := source.global_position.distance_to(player.global_position)
		if player_distance < 55.0 and _has_line_of_sight(source, player) and player_distance < best_distance:
			best = player
			best_distance = player_distance
	for candidate in map_root.find_children("BotSoldier_*", "CharacterBody3D", true, false):
		if candidate == source or not is_instance_valid(candidate) or candidate.get("dead") == true:
			continue
		var candidate_team := int(candidate.get("team_id"))
		if candidate_team == source_team:
			continue
		var distance := source.global_position.distance_to(candidate.global_position)
		if distance < 55.0 and distance < best_distance and _has_line_of_sight(source, candidate):
			best = candidate
			best_distance = distance
	return best

func _has_line_of_sight(source: Node3D, target: Node3D) -> bool:
	var from := source.global_position + Vector3.UP * 1.35
	var to := target.global_position + Vector3.UP * 1.1
	var query := PhysicsRayQueryParameters3D.create(from, to)
	query.collision_mask = 3
	query.exclude = [source.get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	return not hit.is_empty() and hit.collider == target

func bot_shoot(bot: CharacterBody3D) -> void:
	if match_finished or not is_instance_valid(bot) or not is_instance_valid(bot.get("target")):
		return
	var target = bot.get("target")
	var from := bot.global_position + Vector3.UP * 1.35
	var to := target.global_position + Vector3.UP * 1.1
	var query := PhysicsRayQueryParameters3D.create(from, to)
	query.collision_mask = 3
	query.exclude = [bot.get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty() or hit.collider != target:
		return
	var damage := rng.randi_range(6, 11)
	if target == player:
		if dead_timer > 0.0:
			return
		health = maxi(0, health - damage)
		_update_hud()
		if health <= 0:
			dead_timer = 2.2
			player.visible = false
			status_label.text = "ELIMINADO  |  RETORNANDO..."
			player.velocity = Vector3.ZERO
	else:
		target.take_damage(damage, false, int(bot.get("team_id")), false)

func bot_killed(bot: Node3D, victim_team: int = 1, attacker_team: int = 0, attacker_is_player: bool = false) -> void:
	if attacker_is_player:
		kills += 1
	elif attacker_team == 1:
		enemy_kills += 1
	else:
		allied_kills += 1
	if is_instance_valid(kills_label):
		kills_label.text = "ELIMINAÇÕES %d / 20" % kills
	if kills >= 20 and not match_finished:
		match_finished = true
		status_label.text = "VITÓRIA! 20 ELIMINAÇÕES"
		return
	_respawn_bot.call_deferred(bot, victim_team)

func _respawn_bot(bot: Node3D, team_id: int) -> void:
	if not is_instance_valid(bot):
		return
	await get_tree().create_timer(4.0).timeout
	if not is_instance_valid(bot) or match_finished:
		return
	var candidates := _get_original_spawn_positions("generic")
	var reference := _choose_spawn_position(candidates, used_spawn_positions) if not candidates.is_empty() else _map_center() + Vector3(rng.randf_range(-20.0,20.0),0.0,rng.randf_range(-20.0,20.0))
	var floor_hit := _find_floor(reference, 24.0)
	if floor_hit.is_empty():
		floor_hit = _find_floor(_map_center(), 30.0)
	if floor_hit.is_empty():
		push_warning("Bot respawn skipped: no valid floor position found.")
		return
	bot.call("reset_for_respawn", floor_hit.position + Vector3.UP * 0.12)

func _reload() -> void:
	var weapon: Dictionary = WEAPON_CATALOG[weapon_index]
	var capacity := int(weapon["magazine"])
	if reload_timer > 0.0 or ammo >= capacity or reserve_ammo <= 0:
		return
	var reload_duration := float(weapon["reload"])
	if weapon_animation_player and weapon_animation_player.has_clip("Reload"):
		reload_duration = weapon_animation_player.get_duration("Reload")
		weapon_animation_player.play("Reload", 1.0, false)
	reload_timer = reload_duration
	status_label.text = "RECARREGANDO..."
	if reload_player:
		reload_player.play()

func _initialize_weapon_inventory() -> void:
	weapon_magazines.clear()
	weapon_reserves.clear()
	for weapon in WEAPON_CATALOG:
		weapon_magazines.append(int(weapon["magazine"]))
		weapon_reserves.append(int(weapon["reserve"]))
	weapon_index = 0
	ammo = weapon_magazines[0]
	reserve_ammo = weapon_reserves[0]

func _swap_weapon() -> void:
	if reload_timer > 0.0:
		reload_timer = 0.0
		if weapon_animation_player and weapon_animation_player.is_playing_clip("Reload"):
			weapon_animation_player.stop()
	weapon_magazines[weapon_index] = ammo
	weapon_reserves[weapon_index] = reserve_ammo
	weapon_index = (weapon_index + 1) % WEAPON_CATALOG.size()
	ammo = weapon_magazines[weapon_index]
	reserve_ammo = weapon_reserves[weapon_index]
	var weapon: Dictionary = WEAPON_CATALOG[weapon_index]
	camera.fov = 70.0 / float(weapon["zoom"]) if aiming else 70.0
	status_label.text = "ARMA: " + String(weapon["name"])
	_update_hud()

func _toggle_aim() -> void:
	aiming = not aiming
	camera.fov = 70.0 / float(WEAPON_CATALOG[weapon_index]["zoom"]) if aiming else 70.0
	status_label.text = "MIRA ATIVADA" if aiming else "MODO DE DISPARO"

func _toggle_crouch() -> void:
	if dead_timer > 0.0 or not is_instance_valid(player):
		return
	crouching = not crouching
	var collision := player.get_node_or_null("CollisionShape3D") as CollisionShape3D
	if collision and collision.shape is CapsuleShape3D:
		var capsule := collision.shape as CapsuleShape3D
		capsule.height = 1.15 if crouching else 1.8
		collision.position.y = capsule.height * 0.5
	if is_instance_valid(camera_pivot):
		camera_pivot.position.y = 1.02 if crouching else 1.58
	status_label.text = "AGACHADO" if crouching else "EM PÉ"

func _jump() -> void:
	if player.is_on_floor() and dead_timer <= 0.0:
		player.velocity.y = 6.2
		if jump_player:
			jump_player.play()

func _update_hud() -> void:
	if is_instance_valid(health_label):
		health_label.text = "VIDA %d / 100" % health
		health_label.add_theme_color_override("font_color", Color(1.0, 0.36, 0.3) if health < 35 else Color(0.91, 0.96, 1.0))
	if is_instance_valid(ammo_label):
		ammo_label.text = "%s  %02d / %02d" % [String(WEAPON_CATALOG[weapon_index]["name"]), ammo, reserve_ammo]
	if is_instance_valid(kills_label):
		kills_label.text = "ELIMINAÇÕES %d" % kills

func shutdown() -> void:
	get_tree().paused = false
	if is_instance_valid(player):
		player.queue_free()
	if is_instance_valid(map_root):
		for bot in map_root.find_children("BotSoldier_*", "CharacterBody3D", true, false):
			bot.queue_free()
	if is_instance_valid(camera):
		camera.current = false

func _toggle_pause() -> void:
	var paused := not get_tree().paused
	get_tree().paused = paused
	if is_instance_valid(pause_button):
		pause_button.text = "▶" if paused else "Ⅱ"
	if is_instance_valid(status_label):
		status_label.text = "PAUSADO" if paused else "BATALHA EM FLORESTA"

func _exit_combat() -> void:
	if return_callback.is_valid():
		return_callback.call()
