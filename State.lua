local _, addon = ...

local function newDatabase()
    return {
        schemaVersion = 1,
        seen = {},
        window = {
            point = "CENTER",
            x = 0,
            y = 0,
        },
    }
end

local function sanitizeWindow(database)
    if type(database.window) ~= "table" then
        database.window = newDatabase().window
        return
    end

    if type(database.window.point) ~= "string" then
        database.window.point = "CENTER"
    end
    if type(database.window.x) ~= "number" then
        database.window.x = 0
    end
    if type(database.window.y) ~= "number" then
        database.window.y = 0
    end
end

function addon.InitializeState()
    if type(BetterPatchNotesDB) ~= "table"
        or BetterPatchNotesDB.schemaVersion ~= 1
    then
        BetterPatchNotesDB = newDatabase()
    end

    if type(BetterPatchNotesDB.seen) ~= "table" then
        BetterPatchNotesDB.seen = {}
    end
    sanitizeWindow(BetterPatchNotesDB)
    addon.db = BetterPatchNotesDB
end

local function classSeen(classToken)
    local seen = addon.db.seen[classToken]
    if type(seen) ~= "table" then
        seen = {}
        addon.db.seen[classToken] = seen
    end

    return seen
end

function addon.HasUnseen(classToken, channel)
    local versions = addon.PatchNotesData.classChannelVersions[classToken]
    local version = versions[channel]
    if version == "" then
        return false
    end

    return classSeen(classToken)[channel] ~= version
end

function addon.MarkAllSeen(classToken)
    local seen = classSeen(classToken)
    local versions = addon.PatchNotesData.classChannelVersions[classToken]
    seen.live = versions.live
    seen.ptr = versions.ptr
end

function addon.SelectInitialChannel(classToken)
    local liveUnseen = addon.HasUnseen(classToken, "live")
    local ptrUnseen = addon.HasUnseen(classToken, "ptr")

    if liveUnseen and ptrUnseen then
        local dates = addon.PatchNotesData.classLatestDates[classToken]
        local liveDate = dates.live or ""
        local ptrDate = dates.ptr or ""
        if ptrDate > liveDate then
            return "ptr"
        end

        return "live"
    end
    if ptrUnseen then
        return "ptr"
    end

    return "live"
end
