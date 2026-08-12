main(): Unit { try { throw "failure" } catch (error: String) { println(error) } }
