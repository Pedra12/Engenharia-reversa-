extends Node3D

const BOT_SCRIPT = preload("res://combat/combat_bot.gd")
const SOLDIER_MESH_PATH = "res://assets/combat_source/meshes/sk_char_sold_male_01_7088991893364766669.obj"
const UMP_MESH_PATH = "res://assets/combat_source/meshes/UMP_45_2.obj"
const SOLDIER_TEXTURE_PATH = "res://assets/combat_source/textures/SimpleMilitary_Soldier01_Black_-6561600483854028127.png"
const UMP_TEXTURE_PATH = "res://assets/combat_source/textures/UMP_45_Diffuse_-7805003812694618604.png"
const GRASS_STEP_PATH = "res://assets/combat_source/audio/footstep_grass_0_1_footstep_grass_0.wav"
const JUMP_SOUND_PATH = "res://assets/combat_source/audio/Jump_1_Jump.wav"
const RELOAD_VOICE_PATH = "res://assets/combat_source/audio/VO_i_need_to_reload_0_-1743279502966138324_VO_i_need_to_reload_0.wav"

var map_root: Node3D
var return_callback: Callable
var player: CharacterBody3D
var camera: Camera3D
var camera_pivot: Node3D
var weapon_mount: Node3D
var weapon_mesh: MeshInstance3D
var soldier_mesh: Mesh
var soldier_material: StandardMaterial3D
var weapon_material: StandardMaterial3D
var hud: Control
var health_label: Label
var ammo_label: Label
var kills_label: Label
var status_label: Label
var hit_label: Label
var joystick_bg: Panel
var joystick_knob: Panel
var move_vector := Vector2.ZERO
var move_touch_id := -1
var look_touch_id := -1
var look_yaw := 0.0
var look_pitch := -0.10
var health := 100
var ammo := 30
var reserve_ammo := 90
var kills := 0
var fire_cooldown := 0.0
var reload_timer := 0.0
var footstep_timer := 0.0
var aiming := false
var dead_timer := 0.0
var spawn_position := Vector3.ZERO
var grass_player: AudioStreamPlayer3D
var jump_player: AudioStreamPlayer3D
var reload_player: AudioStreamPlayer
var rng := RandomNumberGenerator.new()

func begin(existing_map: Node3D, on_return: Callable) -> void:
	map_root = existing_map
	return_callback = on_return
	rng.randomize()
	_prepare_assets()
	_create_player()
	_create_bots()
	_build_hud()
	print("COMBAT_MODE_READY map=Floresta bots=3 weapon=UMP45")

func _prepare_assets() -> void:
	var soldier_resource = load(SOLDIER_MESH_PATH)
	if soldier_resource is Mesh:
		soldier_mesh = soldier_resource
	soldier_material = StandardMaterial3D.new()
	var soldier_texture = load(SOLDIER_TEXTURE_PATH)
	if soldier_texture is Texture2D:
		soldier_material.albedo_texture = soldier_texture
	soldier_material.roughness = 0.88
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
	if found:
		return bounds.get_center()
	return map_root.global_position

func _create_player() -> void:
	player = CharacterBody3D.new()
	player.name = "CombatPlayer"
	player.collision_layer = 2
	player.collision_mask = 1
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.34
	capsule.height = 1.8
	var collision := CollisionShape3D.new()
	collision.shape = capsule
	collision.position.y = 0.9
	player.add_child(collision)
	if soldier_mesh:
		var body := MeshInstance3D.new()
		body.name = "OriginalSoldierMesh"
		body.mesh = soldier_mesh
		body.material_override = soldier_material
		body.rotation_degrees.x = -90.0
		player.add_child(body)
	map_root.add_child(player)
	var center = _map_center()
	var floor_hit = _find_floor(center)
	if floor_hit.is_empty():
		floor_hit = _find_floor(Vector3(40.0, center.y, 40.0))
	if floor_hit.is_empty():
		spawn_position = center + Vector3.UP * 4.0
		push_warning("Combat spawn fallback used; no safe floor ray was found.")
	else:
		spawn_position = floor_hit.position + Vector3.UP * 0.12
	player.global_position = spawn_position
	camera_pivot = Node3D.new()
	camera_pivot.position = Vector3(0.0, 1.48, 0.0)
	player.add_child(camera_pivot)
	camera = Camera3D.new()
	camera.position = Vector3(0.38, 0.20, 3.75)
	camera.fov = 70.0
	camera.current = true
	camera_pivot.add_child(camera)
	weapon_mount = Node3D.new()
	weapon_mount.position = Vector3(0.34, -0.28, -0.52)
	camera.add_child(weapon_mount)
	var weapon_resource = load(UMP_MESH_PATH)
	if weapon_resource is Mesh:
		weapon_mesh = MeshInstance3D.new()
		weapon_mesh.mesh = weapon_resource
		weapon_mesh.material_override = weapon_material
		weapon_mesh.rotation.y = PI
		weapon_mesh.scale = Vector3.ONE * 1.0
		weapon_mount.add_child(weapon_mesh)
	_create_audio()

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
	reload_player.stream = load(RELOAD_VOICE_PATH)
	reload_player.volume_db = -9.0
	add_child(reload_player)

func _create_bots() -> void:
	if not soldier_mesh:
		push_error("Original soldier mesh missing; refusing to create placeholder enemies.")
		return
	var offsets = [Vector3(10, 0, 4), Vector3(-12, 0, -5), Vector3(5, 0, -15)]
	for index in range(offsets.size()):
		var guess = spawn_position + offsets[index]
		var floor_hit = _find_floor(guess, 10.0)
		if floor_hit.is_empty():
			continue
		var bot = CharacterBody3D.new()
		bot.set_script(BOT_SCRIPT)
		bot.name = "BotSoldier_%02d" % (index + 1)
		map_root.add_child(bot)
		bot.global_position = floor_hit.position + Vector3.UP * 0.12
		bot.call("configure", player, self, soldier_mesh, soldier_material)
	print("COMBAT_BOTS_SPAWNED count=", map_root.find_children("BotSoldier_*", "CharacterBody3D", true, false).size())

func _build_hud() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 30
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
	var screen = get_viewport().get_visible_rect().size
	joystick_bg = Panel.new()
	joystick_bg.position = Vector2(42, screen.y - 192)
	joystick_bg.size = Vector2(142, 142)
	_style_panel(joystick_bg, Color(0.08, 0.12, 0.16, 0.46), 72)
	hud.add_child(joystick_bg)
	joystick_knob = Panel.new()
	joystick_knob.position = Vector2(48, 48)
	joystick_knob.size = Vector2(46, 46)
	_style_panel(joystick_knob, Color(0.62, 0.78, 0.88, 0.72), 24)
	joystick_bg.add_child(joystick_knob)
	_make_button("TIRO", Vector2(-130, -236), Vector2(112, 68), _fire)
	_make_button("MIRA", Vector2(-254, -164), Vector2(108, 62), _toggle_aim)
	_make_button("PULAR", Vector2(-130, -154), Vector2(112, 62), _jump)
	_make_button("RECARREGAR", Vector2(-254, -88), Vector2(108, 58), _reload)
	_make_button("SAIR", Vector2(18, -82), Vector2(88, 54), _exit_combat, false)
	var crosshair := Label.new()
	crosshair.text = "＋"
	crosshair.set_anchors_preset(Control.PRESET_CENTER)
	crosshair.position = Vector2(-12, -22)
	crosshair.add_theme_font_size_override("font_size", 32)
	crosshair.add_theme_color_override("font_color", Color(0.9, 1.0, 0.94, 0.9))
	hud.add_child(crosshair)

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

func _make_button(value: String, offset: Vector2, dimensions: Vector2, callback: Callable, right: bool = true) -> void:
	var button := Button.new()
	button.text = value
	button.size = dimensions
	if right:
		button.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
		button.position = offset
	else:
		button.set_anchors_preset(Control.PRESET_TOP_LEFT)
		button.position = offset
	button.add_theme_font_size_override("font_size", 16)
	button.add_theme_color_override("font_color", Color(0.95, 0.98, 1.0))
	button.pressed.connect(callback)
	hud.add_child(button)

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventScreenTouch:
		var screen = get_viewport().get_visible_rect().size
		if event.pressed:
			if event.position.x < screen.x * 0.42 and event.position.y > screen.y * 0.48 and move_touch_id == -1:
				move_touch_id = event.index
				_update_joystick(event.position)
			elif event.position.x >= screen.x * 0.42 and event.position.y < screen.y - 250 and look_touch_id == -1:
				look_touch_id = event.index
		else:
			if event.index == move_touch_id:
				move_touch_id = -1
				move_vector = Vector2.ZERO
				joystick_knob.position = Vector2(48, 48)
			if event.index == look_touch_id:
				look_touch_id = -1
	elif event is InputEventScreenDrag:
		if event.index == move_touch_id:
			_update_joystick(event.position)
		elif event.index == look_touch_id:
			_apply_look(event.relative)
	elif event is InputEventMouseMotion and Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT):
		_apply_look(event.relative)

func _update_joystick(position: Vector2) -> void:
	var center = joystick_bg.position + joystick_bg.size * 0.5
	var offset = position - center
	if offset.length() > 48.0:
		offset = offset.normalized() * 48.0
	move_vector = Vector2(offset.x / 48.0, -offset.y / 48.0)
	joystick_knob.position = Vector2(48, 48) + offset

func _apply_look(relative: Vector2) -> void:
	look_yaw -= relative.x * 0.004
	look_pitch = clampf(look_pitch - relative.y * 0.003, -0.72, 0.45)
	player.rotation.y = look_yaw
	camera_pivot.rotation.x = look_pitch

func _physics_process(delta: float) -> void:
	if not is_instance_valid(player):
		return
	fire_cooldown = maxf(0.0, fire_cooldown - delta)
	if reload_timer > 0.0:
		reload_timer -= delta
		if reload_timer <= 0.0:
			var needed = 30 - ammo
			var loaded = mini(needed, reserve_ammo)
			ammo += loaded
			reserve_ammo -= loaded
			_update_hud()
	if dead_timer > 0.0:
		dead_timer -= delta
		if dead_timer <= 0.0:
			health = 100
			player.global_position = spawn_position
			player.velocity = Vector3.ZERO
			player.visible = true
			_update_hud()
			status_label.text = "VOCÊ RETORNOU AO COMBATE"
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
	var speed = 3.0 if aiming else 5.0
	player.velocity.x = direction.x * speed
	player.velocity.z = direction.z * speed
	player.move_and_slide()
	if direction.length() > 0.15:
		footstep_timer -= delta
		if footstep_timer <= 0.0 and grass_player and not grass_player.playing:
			grass_player.play()
			footstep_timer = 0.48
	if direction.length() > 0.1 and soldier_mesh:
		var body = player.get_node_or_null("OriginalSoldierMesh") as MeshInstance3D
		if body:
			body.position.y = 0.025 * sin(Time.get_ticks_msec() * 0.018)
	if Input.is_key_pressed(KEY_SPACE):
		_jump()

func _fire() -> void:
	if fire_cooldown > 0.0 or reload_timer > 0.0 or dead_timer > 0.0:
		return
	if ammo <= 0:
		status_label.text = "SEM MUNIÇÃO: RECARREGUE"
		return
	ammo -= 1
	fire_cooldown = 0.12
	weapon_mount.position.z = -0.44
	var tween = create_tween()
	tween.tween_property(weapon_mount, "position:z", -0.52, 0.09)
	var origin = camera.global_position
	var direction = -camera.global_transform.basis.z
	var query = PhysicsRayQueryParameters3D.create(origin, origin + direction * 110.0)
	query.collision_mask = 1
	query.exclude = [player.get_rid()]
	var hit = get_world_3d().direct_space_state.intersect_ray(query)
	if not hit.is_empty():
		var target = hit.collider
		if target and target.has_method("take_damage"):
			var headshot = hit.position.y > target.global_position.y + 1.42
			var damage = 55 if headshot else 28
			var killed = target.take_damage(damage)
			_show_damage(damage, headshot)
			if headshot:
				status_label.text = "TIRO NA CABEÇA"
			if killed:
				kills += 1
				kills_label.text = "ELIMINAÇÕES %d" % kills
				status_label.text = "ALVO ELIMINADO"
	_update_hud()

func _show_damage(amount: int, headshot: bool) -> void:
	hit_label.text = ("HEADSHOT  " if headshot else "") + str(amount)
	hit_label.visible = true
	hit_label.modulate = Color(1.0, 0.78, 0.24, 1.0) if headshot else Color(1.0, 1.0, 1.0, 1.0)
	hit_label.position = Vector2(-80, -62)
	var tween = create_tween()
	tween.tween_property(hit_label, "position", Vector2(-80, -108), 0.42)
	tween.tween_callback(func(): hit_label.visible = false)

func bot_shoot(bot: Node3D) -> void:
	if dead_timer > 0.0 or not is_instance_valid(player):
		return
	var from = bot.global_position + Vector3.UP * 1.35
	var to = player.global_position + Vector3.UP * 1.1
	var query = PhysicsRayQueryParameters3D.create(from, to)
	query.collision_mask = 3
	query.exclude = [bot.get_rid()]
	var hit = get_world_3d().direct_space_state.intersect_ray(query)
	if not hit.is_empty() and hit.collider == player:
		health = maxi(0, health - rng.randi_range(6, 11))
		_update_hud()
		if health <= 0:
			dead_timer = 2.2
			player.visible = false
			status_label.text = "ELIMINADO  |  RETORNANDO..."
			player.velocity = Vector3.ZERO

func bot_killed(_bot: Node3D) -> void:
	kills += 1
	if is_instance_valid(kills_label):
		kills_label.text = "ELIMINAÇÕES %d" % kills

func _reload() -> void:
	if reload_timer > 0.0 or ammo >= 30 or reserve_ammo <= 0:
		return
	reload_timer = 1.35
	status_label.text = "RECARREGANDO..."
	if reload_player:
		reload_player.play()

func _toggle_aim() -> void:
	aiming = not aiming
	camera.fov = 54.0 if aiming else 70.0
	status_label.text = "MIRA ATIVADA" if aiming else "MODO DE DISPARO"

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
		ammo_label.text = "UMP45  %02d / %02d" % [ammo, reserve_ammo]
	if is_instance_valid(kills_label):
		kills_label.text = "ELIMINAÇÕES %d" % kills

func _exit_combat() -> void:
	if return_callback.is_valid():
		return_callback.call()
