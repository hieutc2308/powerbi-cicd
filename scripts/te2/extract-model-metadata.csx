// Read-only TOM metadata and DAX dependency extractor for Tabular Editor 2 CLI.
// Writes JSON to TE2_METADATA_OUT (default: dist/te2-metadata.json). Never modifies the model.

using System.IO;

var outPath = Environment.GetEnvironmentVariable("TE2_METADATA_OUT");
if (string.IsNullOrWhiteSpace(outPath))
{
    outPath = Path.Combine("dist", "te2-metadata.json");
}

var outDir = Path.GetDirectoryName(Path.GetFullPath(outPath));
if (!string.IsNullOrEmpty(outDir) && !Directory.Exists(outDir))
{
    Directory.CreateDirectory(outDir);
}

Func<IDaxDependantObject, List<object>> extractDependsOn = (obj) =>
{
    var deps = new List<object>();
    try
    {
        foreach (var kvp in obj.DependsOn)
        {
            var target = kvp.Key;
            var targetTable = "";
            if (target is Column) targetTable = ((Column)target).Table.Name;
            else if (target is Measure) targetTable = ((Measure)target).Table.Name;
            else if (target is Table) targetTable = ((Table)target).Name;

            var refs = new List<object>();
            foreach (var r in kvp.Value)
            {
                refs.Add(new
                {
                    text = r.ToString(),
                    daxObjectFullName = target.DaxObjectFullName
                });
            }

            deps.Add(new
            {
                objectType = target.ObjectType.ToString(),
                table = targetTable,
                name = target.Name,
                daxObjectFullName = target.DaxObjectFullName,
                references = refs
            });
        }
    }
    catch
    {
        // Ignore dependency errors on malformed expressions; BPA reports them separately.
    }
    return deps;
};

var tables = new List<object>();
foreach (var t in Model.Tables)
{
    var partitions = new List<object>();
    foreach (var p in t.Partitions)
    {
        partitions.Add(new
        {
            name = p.Name,
            sourceType = p.SourceType.ToString(),
            mode = p.Mode.ToString(),
            expression = p.Expression ?? "",
            queryGroup = p.QueryGroup != null ? p.QueryGroup.Name : ""
        });
    }

    var columns = new List<object>();
    foreach (var c in t.Columns)
    {
        var calcExpr = "";
        if (c is CalculatedColumn)
        {
            calcExpr = ((CalculatedColumn)c).Expression ?? "";
        }
        else if (c is CalculatedTableColumn)
        {
            calcExpr = ((CalculatedTableColumn)c).SourceColumn ?? "";
        }

        var deps = new List<object>();
        if (c is IDaxDependantObject)
        {
            deps = extractDependsOn((IDaxDependantObject)c);
        }

        columns.Add(new
        {
            name = c.Name,
            daxObjectFullName = c.DaxObjectFullName,
            columnType = c.Type.ToString(),
            dataType = c.DataType.ToString(),
            sourceColumn = c is DataColumn ? (((DataColumn)c).SourceColumn ?? "") : "",
            expression = calcExpr,
            formatString = c.FormatString ?? "",
            summarizeBy = c.SummarizeBy.ToString(),
            isHidden = c.IsHidden,
            isKey = c.IsKey,
            isAvailableInMdx = c.IsAvailableInMDX,
            displayFolder = c.DisplayFolder ?? "",
            description = c.Description ?? "",
            dataCategory = c.DataCategory ?? "",
            sortByColumn = c.SortByColumn != null ? c.SortByColumn.Name : "",
            dependsOn = deps
        });
    }

    var measures = new List<object>();
    foreach (var m in t.Measures)
    {
        measures.Add(new
        {
            name = m.Name,
            daxObjectFullName = m.DaxObjectFullName,
            expression = m.Expression ?? "",
            formatString = m.FormatString ?? "",
            displayFolder = m.DisplayFolder ?? "",
            description = m.Description ?? "",
            dataCategory = m.DataCategory ?? "",
            isHidden = m.IsHidden,
            dependsOn = extractDependsOn(m)
        });
    }

    var tableDeps = new List<object>();
    if (t is IDaxDependantObject)
    {
        tableDeps = extractDependsOn((IDaxDependantObject)t);
    }

    tables.Add(new
    {
        name = t.Name,
        tableType = t.ObjectTypeName,
        isHidden = t.IsHidden,
        description = t.Description ?? "",
        dataCategory = t.DataCategory ?? "",
        partitions = partitions,
        columns = columns,
        measures = measures,
        dependsOn = tableDeps
    });
}

var relationships = new List<object>();
foreach (var rel in Model.Relationships)
{
    relationships.Add(new
    {
        name = rel.Name,
        fromTable = rel.FromTable.Name,
        fromColumn = rel.FromColumn.Name,
        fromCardinality = rel.FromCardinality.ToString(),
        toTable = rel.ToTable.Name,
        toColumn = rel.ToColumn.Name,
        toCardinality = rel.ToCardinality.ToString(),
        crossFilteringBehavior = rel.CrossFilteringBehavior.ToString(),
        isActive = rel.IsActive,
        securityFilteringBehavior = rel.SecurityFilteringBehavior.ToString()
    });
}

var roles = new List<object>();
foreach (var role in Model.Roles)
{
    var perms = new List<object>();
    foreach (var tp in role.TablePermissions)
    {
        perms.Add(new
        {
            table = tp.Table.Name,
            filterExpression = tp.FilterExpression ?? ""
        });
    }
    roles.Add(new
    {
        name = role.Name,
        modelPermission = role.ModelPermission.ToString(),
        tablePermissions = perms
    });
}

var expressions = new List<object>();
foreach (var expr in Model.Expressions)
{
    expressions.Add(new
    {
        name = expr.Name,
        kind = expr.Kind.ToString(),
        expression = expr.Expression ?? "",
        queryGroup = expr.QueryGroup != null ? expr.QueryGroup.Name : "",
        description = expr.Description ?? ""
    });
}

var queryGroups = new List<object>();
foreach (var qg in Model.QueryGroups)
{
    queryGroups.Add(new
    {
        name = qg.Name,
        description = qg.Description ?? ""
    });
}

var payload = new
{
    model = new
    {
        name = Model.Database != null ? Model.Database.Name : "SemanticModel",
        compatibilityLevel = Model.Database != null ? Model.Database.CompatibilityLevel : 0,
        culture = Model.Culture ?? "",
        queryGroups = queryGroups
    },
    tables = tables,
    relationships = relationships,
    roles = roles,
    expressions = expressions
};

File.WriteAllText(outPath, JsonConvert.SerializeObject(payload, Formatting.Indented));
Info("Exported TOM metadata to " + outPath);
