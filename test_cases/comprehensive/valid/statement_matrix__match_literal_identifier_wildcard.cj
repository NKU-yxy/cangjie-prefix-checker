main(): Unit { let value: Int64 = 1
 match (value) { case 0 => "zero", case other => "other", case _ => "fallback", } }
