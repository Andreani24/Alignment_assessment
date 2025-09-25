function table_print(tt, indent, done)
    done = done or {}
    indent = indent or 0
    if type(tt) == "table" then
        local sb = {}
        for key, value in pairs (tt) do
            table.insert(sb, string.rep(" ", indent))
            if type(value) == "table" and not done[value] then
                done[value] = true
                table.insert(sb, key .. " = {\n");
                table.insert(sb, table_print(value, indent + 2, done))
                table.insert(sb, string.rep(" ", indent))
                table.insert(sb, "}\n");
            elseif "number" == type(key) then
                table.insert(sb, string.format("%s\n", tostring(value)))
            else
                table.insert(sb, string.format("%s = %s\n", tostring(key), tostring(value)))
            end
        end
        return table.concat(sb)
    else
        return tt .. "\n"
    end
end

function write_file(s)
    file = io.open("dump.txt", "w")
    if file then
		file:write(s)
		return "dump to dump.txt ok"
	else
		return "open dump.txt failed"
	end
end

function main(tt, gg)
    local s = table_print(tt)
	local t = table_print(gg)
    return write_file(s .. t)
end