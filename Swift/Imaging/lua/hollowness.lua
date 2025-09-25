function main(tt, gg)
    if #tt == 2 and tt[1].area ~= nil and tt[2].area ~= nil then
		if tt[1].area >= tt[2].area then
			return (100 * tt[2].area) / tt[1].area
		else
			return (100 * tt[1].area) / tt[2].area
		end
	end
end