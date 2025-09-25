function main(tt, gg)
    if #tt == 1 and tt[1].radius[1] ~= nil and tt[1].radius[2] ~= nil then
		return tt[1].radius[1] / tt[1].radius[2]
	end
end