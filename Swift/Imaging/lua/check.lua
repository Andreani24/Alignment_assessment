-- check the length greater than 3.0 cm
function main(tt, gg)
	-- resolution and unit ratio is valid?
	if gg.unitratio <= 0.0 or gg.resolution <= 0.0 then
		return false
	end
	
    for k, v in ipairs(tt) do
		if v.length ~= nil then
			if v.length < 0.03 * gg.unitratio then
				return false
			end
		end
	end
	
	return true
end