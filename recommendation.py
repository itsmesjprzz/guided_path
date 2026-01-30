import sqlite3

def get_recommendations(sat, act, gpa, interests):
    conn = sqlite3.connect('recommendations.db')
    c = conn.cursor()
    c.execute('SELECT name, programs FROM colleges WHERE required_sat <= ? AND required_act <= ? AND min_gpa <= ?',
              (sat, act, gpa))
    matches = c.fetchall()
    conn.close()
    
    # Filter by interests (simple string match)
    recommendations = [f"{name}: {programs}" for name, programs in matches if interests.lower() in programs.lower()]
    return recommendations if recommendations else ["No matches found. Consider retaking exams."]