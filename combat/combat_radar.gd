extends Control

var player: Node3D
var bots: Array = []
var radar_range := 85.0
var forest_map_texture: Texture2D

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	clip_contents = true
	var map_path := _find_forest_minimap("res://assets/unity_original/textures")
	if not map_path.is_empty():
		# Load through Godot's import pipeline. Image.load_from_file(res://...) works
		# in editor runs but bypasses exported resource remapping in Android builds.
		var imported_texture := ResourceLoader.load(map_path) as Texture2D
		var source: Image = imported_texture.get_image() if imported_texture != null else null
		if source != null and not source.is_empty():
			# Preserve the original forest minimap artwork and mask it to the
			# same circular viewport used by the recovered Unity radar.
			var width := source.get_width()
			var height := source.get_height()
			var center := Vector2(width, height) * 0.5
			var radius := minf(width, height) * 0.5
			for y in range(height):
				for x in range(width):
					if Vector2(x + 0.5, y + 0.5).distance_to(center) > radius:
						var pixel := source.get_pixel(x, y)
						pixel.a = 0.0
						source.set_pixel(x, y, pixel)
			forest_map_texture = ImageTexture.create_from_image(source)
			print("BLOCKGUN_RADAR_TEXTURE_READY path=", map_path, " size=", width, "x", height)
		else:
			push_warning("BLOCKGUN_RADAR_TEXTURE_MISSING imported forest minimap: " + map_path)
	else:
		push_warning("BLOCKGUN_RADAR_TEXTURE_MISSING no original forest minimap found")

func _find_forest_minimap(folder_path: String) -> String:
	var directory := DirAccess.open(folder_path)
	if directory == null:
		return ""
	for file_name in directory.get_files():
		if file_name.to_lower().contains("minimap_forest") and file_name.to_lower().ends_with(".png"):
			return folder_path.path_join(file_name)
	for child_name in directory.get_directories():
		var found := _find_forest_minimap(folder_path.path_join(child_name))
		if not found.is_empty():
			return found
	return ""

func update_radar(player_node: Node3D, bot_nodes: Array) -> void:
	player = player_node
	bots = bot_nodes
	queue_redraw()

func _draw() -> void:
	var center := size * 0.5
	var radius := minf(size.x, size.y) * 0.47
	draw_circle(center, radius, Color(0.018, 0.055, 0.072, 0.76))
	if forest_map_texture:
		draw_texture_rect(forest_map_texture, Rect2(center - Vector2.ONE * radius, Vector2.ONE * radius * 2.0), false, Color(1.0, 1.0, 1.0, 0.88))
	draw_circle(center, radius * 0.72, Color(0.035, 0.105, 0.12, 0.12))
	draw_arc(center, radius, 0.0, TAU, 72, Color(0.42, 0.72, 0.78, 0.86), 2.2, true)
	draw_arc(center, radius * 0.66, 0.0, TAU, 64, Color(0.32, 0.61, 0.67, 0.42), 1.0, true)
	draw_arc(center, radius * 0.33, 0.0, TAU, 48, Color(0.32, 0.61, 0.67, 0.32), 1.0, true)
	draw_line(Vector2(center.x - radius, center.y), Vector2(center.x + radius, center.y), Color(0.32, 0.61, 0.67, 0.25), 1.0)
	draw_line(Vector2(center.x, center.y - radius), Vector2(center.x, center.y + radius), Color(0.32, 0.61, 0.67, 0.25), 1.0)

	if is_instance_valid(player):
		var forward := -player.global_transform.basis.z
		var right := player.global_transform.basis.x
		var tip := center + Vector2(forward.x, -forward.z) * radius * 0.31
		var left := center + Vector2(-right.x, right.z) * radius * 0.15
		var right_point := center + Vector2(right.x, -right.z) * radius * 0.15
		draw_colored_polygon(PackedVector2Array([tip, left, right_point]), Color(0.32, 0.86, 0.91, 0.22))
		draw_circle(center, 5.5, Color(0.35, 0.95, 1.0, 1.0))
		draw_arc(center, 7.0, 0.0, TAU, 24, Color(0.82, 0.98, 1.0, 0.95), 1.4, true)

		for bot in bots:
			if not is_instance_valid(bot) or bot.get("dead") == true:
				continue
			var offset: Vector3 = bot.global_position - player.global_position
			var local_x := offset.dot(right)
			var local_forward := offset.dot(forward)
			var normalized := Vector2(local_x, -local_forward) / radar_range
			if normalized.length() > 1.0:
				continue
			var point := center + normalized * radius
			draw_circle(point, 5.0, Color(1.0, 0.28, 0.2, 1.0))
			draw_arc(point, 7.2, 0.0, TAU, 20, Color(1.0, 0.68, 0.45, 0.9), 1.2, true)
