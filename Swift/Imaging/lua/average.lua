function main(tt, gg)
    local sum = 0
	local cnt = 0
    for k, v in ipairs(tt) do
		if v.length ~= nil then
			sum = sum + v.length
			cnt = cnt + 1
		end
	end
	
    return sum / cnt
end